"""
Tests de integración del módulo pipeline — contra PostgreSQL real.

HALLAZGO REAL de la regresión QA externa (sep-2026): mismo caso que
accounting (ver test_accounting_module.py) — este archivo no existía en
el repo real. A diferencia de accounting, STATE.md no afirmaba lo
contrario para pipeline, así que no hay discrepancia documentada que
corregir, solo un gap real de cobertura persistida (STATE.md sí describe
verificaciones manuales "end-to-end" — vía curl contra el servidor real,
no vía un test que quede corriendo en cada regresión futura).
"""
from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy import text

from app.contacts import schemas as contacts_schemas
from app.contacts.services import ContactService
from app.core import models as core_models
from app.pipeline import schemas
from app.pipeline.services import ActivityService, OpportunityService, StageService
from app.database import AsyncSessionLocal
from app.shared.exceptions import ConflictError, NotFoundError, ValidationError


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


@pytest_asyncio.fixture
async def contact(db, company):
    return await ContactService.create_contact(
        db, company_id=company.id, payload=contacts_schemas.ContactCreate(name="Lead Test", is_lead=True), created_by=None
    )


async def _setup_stages(db, company_id):
    """Un pipeline mínimo real: dos etapas abiertas + ganada + perdida."""
    s1 = await StageService.create(db, company_id=company_id, payload=schemas.StageCreate(name="Contacto inicial", sort_order=1))
    s2 = await StageService.create(db, company_id=company_id, payload=schemas.StageCreate(name="Propuesta", sort_order=2))
    won = await StageService.create(db, company_id=company_id, payload=schemas.StageCreate(name="Ganada", sort_order=99, is_won=True))
    lost = await StageService.create(db, company_id=company_id, payload=schemas.StageCreate(name="Perdida", sort_order=100, is_lost=True))
    return s1, s2, won, lost


# ---------------------------------------------------------------------------
# Camino feliz
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_stage_cannot_be_won_and_lost_at_once(db, company):
    with pytest.raises(ValidationError):
        await StageService.create(db, company_id=company.id, payload=schemas.StageCreate(name="Imposible", is_won=True, is_lost=True))


@pytest.mark.asyncio
async def test_create_opportunity_on_existing_contact_and_free_movement_between_open_stages(db, company, contact):
    s1, s2, won, lost = await _setup_stages(db, company.id)

    opp = await OpportunityService.create(
        db, company_id=company.id,
        payload=schemas.OpportunityCreate(contact_id=contact.id, stage_id=s1.id, name="Venta grande", amount=Decimal(5000)),
        created_by=None,
    )
    assert opp.stage_id == s1.id
    assert opp.status == "open"

    # Movimiento libre entre etapas NO terminales — kanban real, sin
    # comando especial.
    moved = await OpportunityService.move_stage(
        db, company_id=company.id, opportunity_id=opp.id, payload=schemas.OpportunityMoveStage(stage_id=s2.id), actor_id=None
    )
    assert moved.stage_id == s2.id
    # Y de vuelta.
    moved_back = await OpportunityService.move_stage(
        db, company_id=company.id, opportunity_id=opp.id, payload=schemas.OpportunityMoveStage(stage_id=s1.id), actor_id=None
    )
    assert moved_back.stage_id == s1.id


@pytest.mark.asyncio
async def test_cannot_create_opportunity_directly_in_terminal_stage(db, company, contact):
    s1, s2, won, lost = await _setup_stages(db, company.id)
    with pytest.raises(ValidationError):
        await OpportunityService.create(
            db, company_id=company.id,
            payload=schemas.OpportunityCreate(contact_id=contact.id, stage_id=won.id, name="No debería poder"),
            created_by=None,
        )


@pytest.mark.asyncio
async def test_cannot_move_directly_to_terminal_stage_must_use_close_command(db, company, contact):
    """DED-18: alcanzar una etapa terminal es un comando explícito
    (close_won/close_lost), nunca un simple move_stage."""
    s1, s2, won, lost = await _setup_stages(db, company.id)
    opp = await OpportunityService.create(
        db, company_id=company.id,
        payload=schemas.OpportunityCreate(contact_id=contact.id, stage_id=s1.id, name="X"),
        created_by=None,
    )
    with pytest.raises(ValidationError):
        await OpportunityService.move_stage(
            db, company_id=company.id, opportunity_id=opp.id, payload=schemas.OpportunityMoveStage(stage_id=won.id), actor_id=None
        )


@pytest.mark.asyncio
async def test_close_won_only_via_explicit_command_never_side_effect(db, company, contact):
    s1, s2, won, lost = await _setup_stages(db, company.id)
    opp = await OpportunityService.create(
        db, company_id=company.id,
        payload=schemas.OpportunityCreate(contact_id=contact.id, stage_id=s1.id, name="Cierre ganado"),
        created_by=None,
    )
    closed = await OpportunityService.close_won(db, company_id=company.id, opportunity_id=opp.id, actor_id=None)
    assert closed.status == "won"
    assert closed.stage_id == won.id
    assert closed.closed_at is not None


@pytest.mark.asyncio
async def test_close_lost_records_reason(db, company, contact):
    s1, s2, won, lost = await _setup_stages(db, company.id)
    opp = await OpportunityService.create(
        db, company_id=company.id,
        payload=schemas.OpportunityCreate(contact_id=contact.id, stage_id=s1.id, name="Cierre perdido"),
        created_by=None,
    )
    closed = await OpportunityService.close_lost(
        db, company_id=company.id, opportunity_id=opp.id,
        payload=schemas.OpportunityCloseLost(lost_reason="Precio"), actor_id=None,
    )
    assert closed.status == "lost"
    assert closed.lost_reason == "Precio"


# ---------------------------------------------------------------------------
# Casos límite
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_moving_already_closed_opportunity_rejected_terminal_is_terminal(db, company, contact):
    """Catálogo módulo 7: mover una oportunidad ya cerrada (ganada o
    perdida) a otra etapa → rechazado, para ambos casos de cierre."""
    s1, s2, won, lost = await _setup_stages(db, company.id)

    opp_won = await OpportunityService.create(
        db, company_id=company.id, payload=schemas.OpportunityCreate(contact_id=contact.id, stage_id=s1.id, name="Ganada"), created_by=None
    )
    await OpportunityService.close_won(db, company_id=company.id, opportunity_id=opp_won.id, actor_id=None)
    with pytest.raises(ConflictError):
        await OpportunityService.move_stage(
            db, company_id=company.id, opportunity_id=opp_won.id, payload=schemas.OpportunityMoveStage(stage_id=s2.id), actor_id=None
        )

    opp_lost = await OpportunityService.create(
        db, company_id=company.id, payload=schemas.OpportunityCreate(contact_id=contact.id, stage_id=s1.id, name="Perdida"), created_by=None
    )
    await OpportunityService.close_lost(db, company_id=company.id, opportunity_id=opp_lost.id, payload=schemas.OpportunityCloseLost(), actor_id=None)
    with pytest.raises(ConflictError):
        await OpportunityService.move_stage(
            db, company_id=company.id, opportunity_id=opp_lost.id, payload=schemas.OpportunityMoveStage(stage_id=s2.id), actor_id=None
        )


@pytest.mark.asyncio
async def test_reopen_closed_opportunity_returns_to_open_stage(db, company, contact):
    s1, s2, won, lost = await _setup_stages(db, company.id)
    opp = await OpportunityService.create(
        db, company_id=company.id, payload=schemas.OpportunityCreate(contact_id=contact.id, stage_id=s1.id, name="X"), created_by=None
    )
    await OpportunityService.close_lost(db, company_id=company.id, opportunity_id=opp.id, payload=schemas.OpportunityCloseLost(), actor_id=None)

    with pytest.raises(ConflictError):
        # ya está cerrada, no se puede reabrir la ya abierta... al revés:
        # cerrar de nuevo una ya cerrada falla.
        await OpportunityService.close_lost(db, company_id=company.id, opportunity_id=opp.id, payload=schemas.OpportunityCloseLost(), actor_id=None)

    reopened = await OpportunityService.reopen(db, company_id=company.id, opportunity_id=opp.id, actor_id=None)
    assert reopened.status == "open"
    assert reopened.closed_at is None
    assert reopened.lost_reason is None
    assert reopened.stage_id in (s1.id, s2.id)  # primera etapa no terminal configurada

    # Ya reabierta: reopen de nuevo es un no-op rechazado (ya está open).
    with pytest.raises(ConflictError):
        await OpportunityService.reopen(db, company_id=company.id, opportunity_id=opp.id, actor_id=None)


# ---------------------------------------------------------------------------
# Multi-tenant
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_activity_from_another_company_never_visible(db):
    """Catálogo módulo 7: actividad asociada a una oportunidad de otra
    compañía → nunca visible ni asociable."""
    unique_a, unique_b = uuid.uuid4().hex[:8], uuid.uuid4().hex[:8]
    company_a = core_models.Company(name=f"A {unique_a}", tax_id=unique_a)
    company_b = core_models.Company(name=f"B {unique_b}", tax_id=unique_b)
    db.add_all([company_a, company_b])
    await db.flush()

    await db.execute(text("SELECT set_config('app.current_company_id', :cid, false)"), {"cid": str(company_a.id)})
    contact_a = await ContactService.create_contact(
        db, company_id=company_a.id, payload=contacts_schemas.ContactCreate(name="Contacto A", is_lead=True), created_by=None
    )
    activity = await ActivityService.create(
        db, company_id=company_a.id,
        payload=schemas.ActivityCreate(contact_id=contact_a.id, activity_type=schemas.ActivityTypeEnum.call, subject="Llamada"),
        created_by=None,
    )
    await db.commit()

    await db.execute(text("SELECT set_config('app.current_company_id', :cid, false)"), {"cid": str(company_b.id)})
    with pytest.raises(NotFoundError):
        await ActivityService.get(db, company_id=company_b.id, activity_id=activity.id)

    result = await db.execute(text("SELECT count(*) FROM activities WHERE id = :aid"), {"aid": activity.id})
    assert result.scalar_one() == 0


@pytest.mark.asyncio
async def test_rls_blocks_cross_tenant_opportunity_read(db):
    unique_a, unique_b = uuid.uuid4().hex[:8], uuid.uuid4().hex[:8]
    company_a = core_models.Company(name=f"A {unique_a}", tax_id=unique_a)
    company_b = core_models.Company(name=f"B {unique_b}", tax_id=unique_b)
    db.add_all([company_a, company_b])
    await db.flush()

    await db.execute(text("SELECT set_config('app.current_company_id', :cid, false)"), {"cid": str(company_a.id)})
    contact_a = await ContactService.create_contact(
        db, company_id=company_a.id, payload=contacts_schemas.ContactCreate(name="Contacto A", is_lead=True), created_by=None
    )
    s1, _, _, _ = await _setup_stages(db, company_a.id)
    opp = await OpportunityService.create(
        db, company_id=company_a.id, payload=schemas.OpportunityCreate(contact_id=contact_a.id, stage_id=s1.id, name="X"), created_by=None
    )
    await db.commit()

    await db.execute(text("SELECT set_config('app.current_company_id', :cid, false)"), {"cid": str(company_b.id)})
    with pytest.raises(NotFoundError):
        await OpportunityService.get(db, company_id=company_b.id, opportunity_id=opp.id)
