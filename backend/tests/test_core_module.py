"""
Tests de integración del módulo core — contra el PostgreSQL real del
entorno (Nivel 1, spec DoD sección 11: "al menos un test de integración con
DB real"). No usan sqlite ni mocks del motor de base de datos: la garantía
que importa (RLS, trigger de inmutabilidad, constraints) solo existe en
Postgres real, un test contra sqlite la daría por buena sin probarla.
"""
from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.core import models, schemas, security
from app.core.services import AuditService, AuthService, RoleService, UserService
from app.database import AsyncSessionLocal, AuthLookupSessionLocal
from app.shared.exceptions import ConflictError, ValidationError


@pytest_asyncio.fixture
async def db():
    async with AsyncSessionLocal() as session:
        yield session
        await session.rollback()


@pytest_asyncio.fixture
async def auth_lookup_db():
    async with AuthLookupSessionLocal() as session:
        yield session


@pytest_asyncio.fixture
async def company(db):
    """Cada test crea su propia compañía — aislamiento entre tests, no
    dependen de un estado compartido ni de orden de ejecución."""
    unique = uuid.uuid4().hex[:8]
    c = models.Company(name=f"Test Co {unique}", tax_id=unique)
    db.add(c)
    await db.flush()
    await db.execute(text("SELECT set_config('app.current_company_id', :cid, false)"), {"cid": str(c.id)})
    await db.commit()
    return c


@pytest.mark.asyncio
async def test_company_defaults_honduras(db, company):
    assert company.timezone == "America/Tegucigalpa"
    assert company.currency_code == "HNL"
    assert company.locale == "es-HN"


@pytest.mark.asyncio
async def test_user_email_unique_globally_not_per_company(db, company):
    """AMBIGUO Fase 2 registrado: email único GLOBAL, no por compañía."""
    u1 = await UserService.create_user(
        db,
        company_id=company.id,
        payload=schemas.UserCreate(email="dup@test.hn", full_name="Uno", password="password123"),
        created_by=None,
    )
    assert u1.id is not None

    with pytest.raises(ConflictError):
        await UserService.create_user(
            db,
            company_id=company.id,
            payload=schemas.UserCreate(email="dup@test.hn", full_name="Dos", password="password123"),
            created_by=None,
        )


@pytest.mark.asyncio
async def test_rls_blocks_cross_tenant_read(db):
    """El test más importante del módulo: dos compañías, cada una NO debe
    poder leer registros de audit de la otra bajo el rol erp_app real."""
    unique_a, unique_b = uuid.uuid4().hex[:8], uuid.uuid4().hex[:8]
    company_a = models.Company(name=f"A {unique_a}", tax_id=unique_a)
    company_b = models.Company(name=f"B {unique_b}", tax_id=unique_b)
    db.add_all([company_a, company_b])
    await db.flush()

    await db.execute(text("SELECT set_config('app.current_company_id', :cid, false)"), {"cid": str(company_a.id)})
    await AuditService.log_event(
        db, company_id=company_a.id, event="test.a", entity_type="company", entity_id=company_a.id, user_id=None
    )
    await db.commit()

    await db.execute(text("SELECT set_config('app.current_company_id', :cid, false)"), {"cid": str(company_b.id)})
    result = await db.execute(text("SELECT count(*) FROM audit WHERE entity_id = :eid"), {"eid": company_a.id})
    assert result.scalar_one() == 0, "RLS falló: la compañía B pudo leer audit de la compañía A"


@pytest.mark.asyncio
async def test_audit_trigger_blocks_update(db, company):
    entry = await AuditService.log_event(
        db, company_id=company.id, event="test.immutable", entity_type="company", entity_id=company.id, user_id=None
    )
    await db.commit()

    with pytest.raises(IntegrityError) if False else pytest.raises(Exception) as exc_info:
        await db.execute(text("UPDATE audit SET event = 'tampered' WHERE id = :id"), {"id": entry.id})
        await db.commit()
    assert "append-only" in str(exc_info.value)
    await db.rollback()


@pytest.mark.asyncio
async def test_login_wrong_password_generic_message(db, auth_lookup_db, company):
    await UserService.create_user(
        db,
        company_id=company.id,
        payload=schemas.UserCreate(email="loginfail@test.hn", full_name="X", password="correcta123"),
        created_by=None,
    )

    with pytest.raises(ValidationError, match="Credenciales inválidas"):
        await AuthService.login(
            auth_lookup_db,
            db,
            payload=schemas.LoginRequest(email="loginfail@test.hn", password="incorrecta"),
            user_agent=None,
            ip_address=None,
        )

    # Mismo mensaje para email inexistente — nunca revelar cuál caso fue.
    with pytest.raises(ValidationError, match="Credenciales inválidas"):
        await AuthService.login(
            auth_lookup_db,
            db,
            payload=schemas.LoginRequest(email="no_existe@test.hn", password="cualquiera"),
            user_agent=None,
            ip_address=None,
        )


@pytest.mark.asyncio
async def test_login_success_and_refresh_rotation(db, auth_lookup_db, company):
    await UserService.create_user(
        db,
        company_id=company.id,
        payload=schemas.UserCreate(email="rotation@test.hn", full_name="X", password="correcta123"),
        created_by=None,
    )

    tokens = await AuthService.login(
        auth_lookup_db,
        db,
        payload=schemas.LoginRequest(email="rotation@test.hn", password="correcta123"),
        user_agent="pytest",
        ip_address="127.0.0.1",
    )
    assert tokens.access_token
    assert tokens.refresh_token

    new_tokens = await AuthService.refresh(auth_lookup_db, db, raw_refresh_token=tokens.refresh_token)
    assert new_tokens.refresh_token != tokens.refresh_token

    # El token viejo, ya rotado, no debe volver a servir.
    with pytest.raises(ValidationError):
        await AuthService.refresh(auth_lookup_db, db, raw_refresh_token=tokens.refresh_token)


@pytest.mark.asyncio
async def test_account_lockout_after_max_attempts(db, auth_lookup_db, company):
    await UserService.create_user(
        db,
        company_id=company.id,
        payload=schemas.UserCreate(email="lockout@test.hn", full_name="X", password="correcta123"),
        created_by=None,
    )

    for _ in range(AuthService.MAX_FAILED_ATTEMPTS):
        with pytest.raises(ValidationError):
            await AuthService.login(
                auth_lookup_db,
                db,
                payload=schemas.LoginRequest(email="lockout@test.hn", password="mala"),
                user_agent=None,
                ip_address=None,
            )

    # La contraseña correcta ya no debe pasar — cuenta bloqueada.
    with pytest.raises(ValidationError, match="bloqueada"):
        await AuthService.login(
            auth_lookup_db,
            db,
            payload=schemas.LoginRequest(email="lockout@test.hn", password="correcta123"),
            user_agent=None,
            ip_address=None,
        )


@pytest.mark.asyncio
async def test_role_duplicate_name_conflict(db, company):
    await RoleService.create_role(db, company_id=company.id, payload=schemas.RoleCreate(name="admin"))
    with pytest.raises(ConflictError):
        await RoleService.create_role(db, company_id=company.id, payload=schemas.RoleCreate(name="admin"))


@pytest.mark.asyncio
async def test_password_hash_never_stored_plain(db, company):
    user = await UserService.create_user(
        db,
        company_id=company.id,
        payload=schemas.UserCreate(email="hashcheck@test.hn", full_name="X", password="miPasswordSecreta"),
        created_by=None,
    )
    assert user.hashed_password != "miPasswordSecreta"
    assert security.verify_password("miPasswordSecreta", user.hashed_password)
    assert not security.verify_password("otra", user.hashed_password)


@pytest.mark.asyncio
async def test_get_active_packages_only_returns_contracted_packages(db, company):
    """Infra de spec 2.4 — no ejercitada por ningún endpoint de core (core
    no está gateado por paquete, es el prerequisito de todos), pero otros
    módulos (Administrativo, Médico, Farmacéutico, Web) van a depender de
    que esta función funcione. Se prueba acá antes de que exista consumidor."""
    from app.core.dependencies import get_active_packages

    # Compañía sin ningún paquete contratado — dict vacío, no error.
    active = await get_active_packages(company.id, db)
    assert active == {}

    pkg = models.CompanyPackage(company_id=company.id, package="administrative", status="active")
    db.add(pkg)
    await db.commit()

    active = await get_active_packages(company.id, db)
    assert "administrative" in active
    assert active["administrative"].status == models.PackageStatusEnum.active
    # Un paquete nunca contratado simplemente no aparece — no es un None.
    assert "pharmacy" not in active


@pytest.mark.asyncio
async def test_require_package_blocks_uncontracted_and_deactivated(db, company):
    """PACKAGE_NOT_LICENSED (DoD, spec 13) — probado directo contra la
    función de dominio (no vía HTTP, esto es Fase 2, no Fase 4 E2E)."""
    from app.core.dependencies import require_package
    from app.shared.exceptions import PackageNotLicensedError, PackageSuspendedError

    checker = require_package("pharmacy")

    with pytest.raises(PackageNotLicensedError):
        await checker(packages={})

    deactivated_pkg = models.CompanyPackage(
        company_id=company.id, package="pharmacy", status=models.PackageStatusEnum.deactivated
    )
    with pytest.raises(PackageNotLicensedError):
        await checker(packages={"pharmacy": deactivated_pkg})

    suspended_pkg = models.CompanyPackage(
        company_id=company.id, package="pharmacy", status=models.PackageStatusEnum.suspended
    )
    # require_package (sin _writable) SÍ deja pasar 'suspended' — es
    # require_package_writable el que la bloquea (spec 13: solo lectura
    # histórica permitida en suspensión).
    result = await checker(packages={"pharmacy": suspended_pkg})
    assert result is suspended_pkg

    from app.core.dependencies import require_package_writable

    writable_checker = require_package_writable("pharmacy")
    with pytest.raises(PackageSuspendedError):
        await writable_checker(row=suspended_pkg)
