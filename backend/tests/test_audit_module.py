"""
Tests de integración del módulo 25 (audit completo) — contra PostgreSQL
real, mismo patrón que el resto de `tests/test_*_module.py`.

VERIFICADO contra Postgres real (sesión de verificación externa,
sep-2026): 5/5 tests de este archivo en verde tras corregir un bug real
en el helper `_log` — intentaba backdatear un evento con `UPDATE audit
SET created_at = ...`, que el propio trigger `trg_audit_immutable` de
este módulo bloquea incondicionalmente (ver AMB-07 en
`app/audit/models.py`). Corregido fijando `created_at` en el INSERT
directamente, sin pasar por UPDATE.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from sqlalchemy import text

from app.audit import schemas as audit_schemas
from app.audit.services import DEFAULT_RETENTION_DAYS, AuditQueryService, AuditRetentionService
from app.core import models as core_models
from app.core.services import AuditService
from app.database import AsyncSessionLocal


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


async def _log(db, company, *, event, entity_type="contact", entity_id=1, user_id=None, changes=None, created_at=None):
    if created_at is not None:
        # `AuditLog.created_at` tiene server_default `now()`, pero un
        # valor explícito en el INSERT lo pisa sin problema — el trigger
        # `trg_audit_immutable` (spec 8.0) solo bloquea UPDATE/DELETE, no
        # INSERT. La versión anterior de este helper hacía INSERT (vía
        # AuditService.log_event) y LUEGO un UPDATE para simular un
        # evento "viejo" — eso viola el propio trigger de inmutabilidad
        # que este módulo describe como incondicional (ver AMB-07 en
        # `app/audit/models.py`), y por eso pytest fallaba con
        # `InsufficientPrivilegeError` contra Postgres real (hallazgo
        # real de la sesión de verificación externa, sep-2026). Se
        # construye el registro directamente con `created_at` ya fijado
        # antes del único INSERT, en vez de pasar por
        # `AuditService.log_event` (que no expone ese parámetro a
        # propósito — la app nunca necesita backdatear un evento real).
        entry = core_models.AuditLog(
            company_id=company.id, event=event, entity_type=entity_type, entity_id=entity_id,
            user_id=user_id, correlation_id=str(uuid.uuid4()), changes=changes, created_at=created_at,
        )
        db.add(entry)
        await db.flush()
    else:
        entry = await AuditService.log_event(
            db, company_id=company.id, event=event, entity_type=entity_type, entity_id=entity_id,
            user_id=user_id, changes=changes,
        )
    await db.commit()
    return entry


@pytest.mark.asyncio
async def test_log_event_stores_changes_diff(db, company):
    entry = await _log(
        db, company, event="sales.order.update", entity_type="sales_order", entity_id=42,
        changes={"status": {"before": "draft", "after": "confirmed"}},
    )
    assert entry.changes == {"status": {"before": "draft", "after": "confirmed"}}


@pytest.mark.asyncio
async def test_log_event_without_changes_stays_null(db, company):
    entry = await _log(db, company, event="contacts.contact.create", entity_type="contact", entity_id=1)
    assert entry.changes is None


@pytest.mark.asyncio
async def test_list_events_filters_by_entity_type_and_event(db, company):
    await _log(db, company, event="sales.order.create", entity_type="sales_order", entity_id=1)
    await _log(db, company, event="sales.order.confirm", entity_type="sales_order", entity_id=1)
    await _log(db, company, event="inventory.stock.write", entity_type="stock_movement", entity_id=9)

    by_entity = await AuditQueryService.list_events(db, company_id=company.id, entity_type="sales_order")
    assert len(by_entity) == 2

    by_event = await AuditQueryService.list_events(db, company_id=company.id, event="inventory.stock.write")
    assert len(by_event) == 1
    assert by_event[0].entity_type == "stock_movement"


@pytest.mark.asyncio
async def test_list_events_filters_by_date_range_and_orders_desc(db, company):
    old = await _log(
        db, company, event="core.user.create", entity_id=1,
        created_at=datetime.now(timezone.utc) - timedelta(days=200),
    )
    recent = await _log(db, company, event="core.user.create", entity_id=2)

    results = await AuditQueryService.list_events(
        db, company_id=company.id, date_from=datetime.now(timezone.utc) - timedelta(days=10),
    )
    ids = [r.id for r in results]
    assert recent.id in ids
    assert old.id not in ids


@pytest.mark.asyncio
async def test_list_events_respects_limit_and_offset(db, company):
    for i in range(5):
        await _log(db, company, event="core.user.create", entity_id=i)

    page1 = await AuditQueryService.list_events(db, company_id=company.id, limit=2, offset=0)
    page2 = await AuditQueryService.list_events(db, company_id=company.id, limit=2, offset=2)
    assert len(page1) == 2
    assert len(page2) == 2
    assert {r.id for r in page1}.isdisjoint({r.id for r in page2})


@pytest.mark.asyncio
async def test_retention_policy_defaults_to_90_days_without_a_row(db, company):
    days = await AuditRetentionService.get_retention_days(db, company_id=company.id)
    assert days == DEFAULT_RETENTION_DAYS == 90

    policy = await AuditRetentionService.get_policy(db, company_id=company.id)
    assert policy is None


@pytest.mark.asyncio
async def test_retention_policy_set_creates_then_updates_same_row(db, company):
    first = await AuditRetentionService.set_policy(
        db, company_id=company.id, payload=audit_schemas.AuditRetentionPolicyUpdate(retention_days=30)
    )
    assert first.retention_days == 30

    second = await AuditRetentionService.set_policy(
        db, company_id=company.id, payload=audit_schemas.AuditRetentionPolicyUpdate(retention_days=180)
    )
    assert second.id == first.id, "Debe actualizar la misma fila, no crear una segunda"
    assert second.retention_days == 180


@pytest.mark.asyncio
async def test_count_purge_eligible_excludes_medical_events_and_recent_rows(db, company):
    await AuditRetentionService.set_policy(
        db, company_id=company.id, payload=audit_schemas.AuditRetentionPolicyUpdate(retention_days=30)
    )
    old_ts = datetime.now(timezone.utc) - timedelta(days=60)

    # Elegible: evento operativo general, vencido.
    await _log(db, company, event="sales.order.create", entity_id=1, created_at=old_ts)
    # NO elegible: mismo tan vencido, pero es un evento clínico (spec 8.1/8.2).
    await _log(db, company, event="medical.record.read", entity_type="clinical_record_entry", entity_id=1, created_at=old_ts)
    # NO elegible: operativo pero todavía dentro de la ventana de retención.
    await _log(db, company, event="sales.order.create", entity_id=2)

    result = await AuditRetentionService.count_purge_eligible(db, company_id=company.id)
    assert result.retention_days == 30
    assert result.eligible_count == 1
    assert result.excluded_medical_count == 1


@pytest.mark.asyncio
async def test_purge_eligible_isolated_per_company(db, company):
    unique = uuid.uuid4().hex[:8]
    other_company = core_models.Company(name=f"Otra Co {unique}", tax_id=unique)
    db.add(other_company)
    await db.flush()
    await db.commit()

    old_ts = datetime.now(timezone.utc) - timedelta(days=200)
    await _log(db, company, event="sales.order.create", entity_id=1, created_at=old_ts)

    await db.execute(text("SELECT set_config('app.current_company_id', :cid, false)"), {"cid": str(other_company.id)})
    result_other = await AuditRetentionService.count_purge_eligible(db, company_id=other_company.id)
    assert result_other.eligible_count == 0

    await db.execute(text("SELECT set_config('app.current_company_id', :cid, false)"), {"cid": str(company.id)})
    result_mine = await AuditRetentionService.count_purge_eligible(db, company_id=company.id)
    assert result_mine.eligible_count == 1
