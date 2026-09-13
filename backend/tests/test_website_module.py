"""
Tests de integración del módulo website — contra PostgreSQL real, mismo
patrón que tests/test_contacts_module.py.

NOTA DE ESTE CIERRE: escritos y revisados estáticamente (sintaxis,
imports, consistencia de firmas con services.py/models.py) pero NO
ejecutados contra una base real en esta sesión — el entorno de diseño no
tenía acceso a un Postgres vivo ni a red para instalar asyncpg. Antes de
marcar el módulo 22 (✓ Completo) en STATE.md, correr
`pytest tests/test_website_module.py` contra una base real, igual que se
exige para cualquier otro módulo del proyecto (spec 11, DoD).
"""
from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from sqlalchemy import text

from app.contacts.models import Contact
from app.core import models as core_models
from app.database import AsyncSessionLocal
from app.shared.exceptions import NotFoundError, ValidationError
from app.website import schemas as website_schemas
from app.website.services import FormSubmissionService, PageService


@pytest_asyncio.fixture
async def db():
    async with AsyncSessionLocal() as session:
        yield session
        await session.rollback()


@pytest_asyncio.fixture
async def company(db):
    unique = uuid.uuid4().hex[:8]
    c = core_models.Company(name=f"Test Co {unique}", tax_id=unique)
    db.add(c)
    await db.flush()
    await db.execute(text("SELECT set_config('app.current_company_id', :cid, false)"), {"cid": str(c.id)})
    await db.commit()
    return c


@pytest.mark.asyncio
async def test_create_page_starts_as_draft(db, company):
    page = await PageService.create_page(
        db,
        company_id=company.id,
        payload=website_schemas.PageCreate(slug="quienes-somos", title="Quiénes Somos", content="<p>Hola</p>"),
        created_by=None,
    )
    assert page.status == "draft"
    assert page.published_at is None


@pytest.mark.asyncio
async def test_publish_and_unpublish_page(db, company):
    page = await PageService.create_page(
        db,
        company_id=company.id,
        payload=website_schemas.PageCreate(slug="terminos", title="Términos", content="..."),
        created_by=None,
    )

    published = await PageService.publish_page(db, company_id=company.id, page_id=page.id, updated_by=None)
    assert published.status == "published"
    assert published.published_at is not None

    with pytest.raises(ValidationError):
        await PageService.publish_page(db, company_id=company.id, page_id=page.id, updated_by=None)

    unpublished = await PageService.unpublish_page(db, company_id=company.id, page_id=page.id, updated_by=None)
    assert unpublished.status == "draft"


@pytest.mark.asyncio
async def test_public_slug_lookup_only_returns_published(db, company):
    page = await PageService.create_page(
        db,
        company_id=company.id,
        payload=website_schemas.PageCreate(slug="landing", title="Landing", content="..."),
        created_by=None,
    )

    with pytest.raises(NotFoundError):
        await PageService.get_published_page_by_slug(db, company_id=company.id, slug="landing")

    await PageService.publish_page(db, company_id=company.id, page_id=page.id, updated_by=None)
    found = await PageService.get_published_page_by_slug(db, company_id=company.id, slug="landing")
    assert found.id == page.id


@pytest.mark.asyncio
async def test_slug_unique_per_company(db, company):
    await PageService.create_page(
        db,
        company_id=company.id,
        payload=website_schemas.PageCreate(slug="landing", title="Landing", content="..."),
        created_by=None,
    )
    with pytest.raises(Exception):
        # Viola uq_website_pages_company_slug — se espera un error real de
        # integridad de Postgres (IntegrityError), no un 4xx de dominio:
        # el servicio no valida unicidad en Python, delega en el
        # constraint de base, mismo criterio que el resto del proyecto
        # para invariantes que la base puede garantizar de forma atómica.
        await PageService.create_page(
            db,
            company_id=company.id,
            payload=website_schemas.PageCreate(slug="landing", title="Landing Duplicada", content="..."),
            created_by=None,
        )


@pytest.mark.asyncio
async def test_form_submission_creates_lead_contact(db, company):
    submission = await FormSubmissionService.submit(
        db,
        company_id=company.id,
        payload=website_schemas.FormSubmissionCreate(
            form_name="contacto", name="Juan Pérez", email="juan@example.com", phone="+504 9999-0000",
            message="Quiero más información",
        ),
    )
    assert submission.contact_id is not None

    result = await db.execute(
        text("SELECT is_lead, email FROM contacts WHERE id = :id"), {"id": submission.contact_id}
    )
    row = result.one()
    assert row.is_lead is True
    assert row.email == "juan@example.com"


@pytest.mark.asyncio
async def test_form_submission_reuses_existing_contact_by_email(db, company):
    existing = Contact(company_id=company.id, name="Cliente Existente", email="repetido@example.com", is_customer=True)
    db.add(existing)
    await db.flush()
    await db.commit()

    submission = await FormSubmissionService.submit(
        db,
        company_id=company.id,
        payload=website_schemas.FormSubmissionCreate(
            form_name="contacto", name="Cliente Existente", email="repetido@example.com",
        ),
    )
    assert submission.contact_id == existing.id

    await db.refresh(existing)
    assert existing.is_lead is True  # se marca is_lead=true aunque ya fuera is_customer
    assert existing.is_customer is True  # no pisa el flag existente


@pytest.mark.asyncio
async def test_rls_blocks_cross_tenant_page_read(db):
    """Mismo test crítico que en contacts, ahora para website_pages."""
    unique_a, unique_b = uuid.uuid4().hex[:8], uuid.uuid4().hex[:8]
    company_a = core_models.Company(name=f"A {unique_a}", tax_id=unique_a)
    company_b = core_models.Company(name=f"B {unique_b}", tax_id=unique_b)
    db.add_all([company_a, company_b])
    await db.flush()

    await db.execute(text("SELECT set_config('app.current_company_id', :cid, false)"), {"cid": str(company_a.id)})
    from app.website import models as website_models

    page = website_models.Page(company_id=company_a.id, slug="solo-a", title="Solo A")
    db.add(page)
    await db.commit()

    await db.execute(text("SELECT set_config('app.current_company_id', :cid, false)"), {"cid": str(company_b.id)})
    result = await db.execute(text("SELECT count(*) FROM website_pages WHERE id = :id"), {"id": page.id})
    assert result.scalar_one() == 0, "RLS falló: la compañía B pudo leer una página de la compañía A"
