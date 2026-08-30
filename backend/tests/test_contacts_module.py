"""
Tests de integración del módulo contacts — contra PostgreSQL real.
Reutiliza el patrón de tests/test_core_module.py (misma fixture `db`,
`company` — ver ahí para el rationale de por qué contra DB real).
"""
from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from sqlalchemy import text

from app.contacts import models as contacts_models
from app.contacts import schemas as contacts_schemas
from app.contacts.services import ContactService
from app.database import AsyncSessionLocal
from app.shared.exceptions import NotFoundError
from pydantic import ValidationError as PydanticValidationError


@pytest_asyncio.fixture
async def db():
    async with AsyncSessionLocal() as session:
        yield session
        await session.rollback()


@pytest_asyncio.fixture
async def company(db):
    from app.core import models as core_models

    unique = uuid.uuid4().hex[:8]
    c = core_models.Company(name=f"Test Co {unique}", tax_id=unique)
    db.add(c)
    await db.flush()
    await db.execute(text("SELECT set_config('app.current_company_id', :cid, false)"), {"cid": str(c.id)})
    await db.commit()
    return c


@pytest.mark.asyncio
async def test_contact_requires_at_least_one_role():
    with pytest.raises(PydanticValidationError, match="al menos un rol activo"):
        contacts_schemas.ContactCreate(name="Sin Rol")


@pytest.mark.asyncio
async def test_create_and_get_contact(db, company):
    contact = await ContactService.create_contact(
        db,
        company_id=company.id,
        payload=contacts_schemas.ContactCreate(name="Ferretería El Roble", is_customer=True),
        created_by=None,
    )
    assert contact.id is not None
    assert contact.is_customer is True
    assert contact.is_vendor is False

    fetched = await ContactService.get_contact(db, company_id=company.id, contact_id=contact.id)
    assert fetched.name == "Ferretería El Roble"


@pytest.mark.asyncio
async def test_get_contact_wrong_company_raises_not_found(db, company):
    """Anti-IDOR a nivel de servicio: el filtro explícito por company_id
    (no solo RLS) debe bloquear el acceso cruzado."""
    contact = await ContactService.create_contact(
        db,
        company_id=company.id,
        payload=contacts_schemas.ContactCreate(name="Solo de Company A", is_customer=True),
        created_by=None,
    )

    with pytest.raises(NotFoundError):
        await ContactService.get_contact(db, company_id=999999, contact_id=contact.id)


@pytest.mark.asyncio
async def test_search_trigram_tolerates_typos(db, company):
    await ContactService.create_contact(
        db,
        company_id=company.id,
        payload=contacts_schemas.ContactCreate(name="Farmacia Central Tegucigalpa", is_customer=True),
        created_by=None,
    )
    await ContactService.create_contact(
        db,
        company_id=company.id,
        payload=contacts_schemas.ContactCreate(name="Distribuidora San José", is_vendor=True),
        created_by=None,
    )

    # Typo deliberado + sin tilde — pg_trgm debe encontrarlo igual.
    results = await ContactService.list_contacts(db, company_id=company.id, search="Farmasia Sentral")
    assert len(results) >= 1
    assert results[0].name == "Farmacia Central Tegucigalpa"


@pytest.mark.asyncio
async def test_update_contact_partial(db, company):
    contact = await ContactService.create_contact(
        db,
        company_id=company.id,
        payload=contacts_schemas.ContactCreate(name="Original", is_customer=True),
        created_by=None,
    )

    updated = await ContactService.update_contact(
        db,
        company_id=company.id,
        contact_id=contact.id,
        payload=contacts_schemas.ContactUpdate(phone="+504 9999-9999"),
        updated_by=None,
    )
    assert updated.phone == "+504 9999-9999"
    assert updated.name == "Original"  # no tocado por el update parcial


@pytest.mark.asyncio
async def test_rls_blocks_cross_tenant_contact_read(db):
    """Mismo test crítico que en core, ahora para contacts."""
    unique_a, unique_b = uuid.uuid4().hex[:8], uuid.uuid4().hex[:8]
    from app.core import models as core_models

    company_a = core_models.Company(name=f"A {unique_a}", tax_id=unique_a)
    company_b = core_models.Company(name=f"B {unique_b}", tax_id=unique_b)
    db.add_all([company_a, company_b])
    await db.flush()

    await db.execute(text("SELECT set_config('app.current_company_id', :cid, false)"), {"cid": str(company_a.id)})
    contact = contacts_models.Contact(company_id=company_a.id, name="Solo A", is_customer=True)
    db.add(contact)
    await db.commit()

    await db.execute(text("SELECT set_config('app.current_company_id', :cid, false)"), {"cid": str(company_b.id)})
    result = await db.execute(text("SELECT count(*) FROM contacts WHERE id = :id"), {"id": contact.id})
    assert result.scalar_one() == 0, "RLS falló: la compañía B pudo leer un contacto de la compañía A"
