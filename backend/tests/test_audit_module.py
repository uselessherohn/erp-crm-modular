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


# ---------------------------------------------------------------------------
# Catálogo módulo 25 — AMB-07, "el caso más importante de este módulo".
# Test explícito y dedicado: la evidencia previa (docstring de arriba)
# era indirecta, encontrada como efecto colateral de un bug en el
# helper de test, no una confirmación directa y a propósito.
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_audit_table_truly_immutable_against_real_erp_app_credentials(db, company):
    """Con Postgres real y las credenciales REALES de erp_app (el rol de
    runtime de la API — `db` usa AsyncSessionLocal, que conecta como
    erp_app, no como superusuario). Si esto alguna vez pasa sin
    excepción, es el hallazgo más grave de toda la auditoría — reportar
    primero, antes que cualquier otro resultado de esta corrida."""
    from sqlalchemy.exc import DBAPIError

    log = await AuditService.log_event(
        db, company_id=company.id, event="test.immutability_check", entity_type="contact", entity_id=1, user_id=None,
    )
    await db.commit()
    log_id = log.id  # capturado ANTES de cualquier rollback — mismo
    # footgun de SQLAlchemy async ya documentado en contacts (STATE.md
    # módulo 2): tocar un atributo de un objeto de una sesión después de
    # un rollback() sin un refresh async explícito revienta con
    # MissingGreenlet. company.id también se captura acá por la misma
    # razón — el fixture `company` comparte esta misma sesión `db`.
    company_id = company.id

    with pytest.raises(DBAPIError) as update_exc:
        await db.execute(text("UPDATE audit SET event = 'tampered' WHERE id = :id"), {"id": log_id})
    assert "append-only" in str(update_exc.value) or "not allowed" in str(update_exc.value).lower()
    await db.rollback()

    with pytest.raises(DBAPIError) as delete_exc:
        await db.execute(text("DELETE FROM audit WHERE id = :id"), {"id": log_id})
    assert "append-only" in str(delete_exc.value) or "not allowed" in str(delete_exc.value).lower()
    await db.rollback()

    # La fila sigue intacta, sin alterar — ninguno de los dos intentos
    # tuvo efecto real (el trigger aborta la transacción, no solo avisa).
    await db.execute(text("SELECT set_config('app.current_company_id', :cid, false)"), {"cid": str(company_id)})
    result = await db.execute(text("SELECT event FROM audit WHERE id = :id"), {"id": log_id})
    assert result.scalar_one() == "test.immutability_check"


@pytest.mark.asyncio
async def test_no_http_delete_endpoint_exists_for_audit(company):
    """Catálogo módulo 25: confirmar que no existe ningún endpoint HTTP
    que borre — el borrado real es scripts/purge_audit.py, fuera de la
    API, con credenciales de owner de tabla. Chequeo directo de las
    rutas registradas, no una suposición."""
    from app.audit.routers import router

    all_methods: set[str] = set()
    for route in router.routes:
        if hasattr(route, "methods") and route.methods:
            all_methods |= route.methods
    assert "DELETE" not in all_methods
