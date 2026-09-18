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

from app import models_registry  # noqa: F401  (registra todos los modelos — user.active_warehouse_id -> warehouses; sin esto, correr este archivo AISLADO falla con NoReferencedTableError. Mismo patrón que ya usan test_medical_module.py/test_notifications_module.py/test_pharmacy_module.py — faltaba acá, irónicamente donde se define la FK problemática. Hallazgo real de la regresión QA externa, sep-2026.)
from app.core import models, schemas, security
from app.core.services import AuditService, AuthService, RoleService, UserService, PasswordResetService, TwoFactorService
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
    """AMBIGUO Fase 2 registrado: email único GLOBAL, no por compañía.

    Email sufijado con uuid (hallazgo real de la regresión QA, sep-2026):
    el literal fijo "dup@test.hn" + db.commit() real hacía que este test
    NO fuera re-corrible contra la misma base persistente — la segunda
    corrida (ej. suite completa después de correr este archivo aislado)
    chocaba con datos reales dejados por la corrida anterior, sin que
    hubiera ningún bug de la app. Mismo patrón de sufijo único que ya usa
    el fixture `company`."""
    unique = uuid.uuid4().hex[:8]
    dup_email = f"dup_{unique}@test.hn"
    u1 = await UserService.create_user(
        db,
        company_id=company.id,
        payload=schemas.UserCreate(email=dup_email, full_name="Uno", password="password123"),
        created_by=None,
    )
    assert u1.id is not None

    with pytest.raises(ConflictError):
        await UserService.create_user(
            db,
            company_id=company.id,
            payload=schemas.UserCreate(email=dup_email, full_name="Dos", password="password123"),
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
async def test_attachment_cross_tenant_returns_not_found_never_permission_denied(db):
    """Catálogo de regresión, módulo 1: adjuntos multi-tenant. Sección 3.4
    del spec de regresión — un intento de leer un recurso de otro tenant
    debe dar NotFoundError, nunca PermissionDeniedError (eso confirmaría
    que el recurso existe en otro lado, fuga de información por el canal
    de error). AttachmentService.get filtra explícitamente por
    company_id (defensa en profundidad además de RLS/FORCE ya verificado
    en test_rls_blocks_cross_tenant_read)."""
    from app.core.services import AttachmentService

    unique_a, unique_b = uuid.uuid4().hex[:8], uuid.uuid4().hex[:8]
    company_a = models.Company(name=f"A {unique_a}", tax_id=unique_a)
    company_b = models.Company(name=f"B {unique_b}", tax_id=unique_b)
    db.add_all([company_a, company_b])
    await db.flush()

    await db.execute(text("SELECT set_config('app.current_company_id', :cid, false)"), {"cid": str(company_a.id)})
    user_a = await UserService.create_user(
        db,
        company_id=company_a.id,
        payload=schemas.UserCreate(email=f"uploader_{unique_a}@test.hn", full_name="Uploader A", password="miPasswordSecreta"),
        created_by=None,
    )
    await db.flush()
    attachment_a = models.Attachment(
        company_id=company_a.id,
        entity_type="test_entity",
        entity_id=1,
        filename="doc.pdf",
        mime_type="application/pdf",
        storage_path="/tmp/doc.pdf",
        uploaded_by=user_a.id,
    )
    db.add(attachment_a)
    await db.commit()

    # Cambio de contexto de tenant a la compañía B — el adjunto es de A.
    await db.execute(text("SELECT set_config('app.current_company_id', :cid, false)"), {"cid": str(company_b.id)})
    found = await AttachmentService.get(db, company_id=company_b.id, attachment_id=attachment_a.id)
    assert found is None, "Fuga cross-tenant: la compañía B pudo leer un adjunto de la compañía A"

    # Confirmación adicional a nivel RLS puro (sin el filtro explícito de
    # company_id, solo la policy) — mismo patrón que test_rls_blocks_cross_tenant_read.
    result = await db.execute(text("SELECT count(*) FROM attachments WHERE id = :aid"), {"aid": attachment_a.id})
    assert result.scalar_one() == 0, "RLS falló: la compañía B pudo ver la fila del adjunto de la compañía A directo por SQL"


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
    unique = uuid.uuid4().hex[:8]
    await UserService.create_user(
        db,
        company_id=company.id,
        payload=schemas.UserCreate(email=f"loginfail_{unique}@test.hn", full_name="X", password="correcta123"),
        created_by=None,
    )

    with pytest.raises(ValidationError, match="Credenciales inválidas"):
        await AuthService.login(
            auth_lookup_db,
            db,
            payload=schemas.LoginRequest(email=f"loginfail_{unique}@test.hn", password="incorrecta"),
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
    unique = uuid.uuid4().hex[:8]
    await UserService.create_user(
        db,
        company_id=company.id,
        payload=schemas.UserCreate(email=f"rotation_{unique}@test.hn", full_name="X", password="correcta123"),
        created_by=None,
    )

    tokens = await AuthService.login(
        auth_lookup_db,
        db,
        payload=schemas.LoginRequest(email=f"rotation_{unique}@test.hn", password="correcta123"),
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
    unique = uuid.uuid4().hex[:8]
    await UserService.create_user(
        db,
        company_id=company.id,
        payload=schemas.UserCreate(email=f"lockout_{unique}@test.hn", full_name="X", password="correcta123"),
        created_by=None,
    )

    for _ in range(AuthService.MAX_FAILED_ATTEMPTS):
        with pytest.raises(ValidationError):
            await AuthService.login(
                auth_lookup_db,
                db,
                payload=schemas.LoginRequest(email=f"lockout_{unique}@test.hn", password="mala"),
                user_agent=None,
                ip_address=None,
            )

    # La contraseña correcta ya no debe pasar — cuenta bloqueada.
    with pytest.raises(ValidationError, match="bloqueada"):
        await AuthService.login(
            auth_lookup_db,
            db,
            payload=schemas.LoginRequest(email=f"lockout_{unique}@test.hn", password="correcta123"),
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
    unique = uuid.uuid4().hex[:8]
    user = await UserService.create_user(
        db,
        company_id=company.id,
        payload=schemas.UserCreate(email=f"hashcheck_{unique}@test.hn", full_name="X", password="miPasswordSecreta"),
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


@pytest.mark.asyncio
async def test_require_package_minimal_module_bug_fix(company):
    """Regresión del bug real encontrado en el cierre del módulo 22
    (website): la condición original de `minimal_module` nunca bloqueaba
    nada porque `row.package != package` era código muerto (`row` siempre
    sale de `packages.get(package)`, así que `row.package == package`
    siempre). Sin consumidor real todavía (ningún router pasa
    `minimal_module=`), así que este test prueba la función de dominio
    directo, no vía HTTP — igual que
    `test_require_package_blocks_uncontracted_and_deactivated` arriba."""
    from app.core.dependencies import require_package
    from app.shared.exceptions import PackageNotLicensedError

    checker = require_package("administrative", minimal_module="sales")

    # Arrastre real (ej. Farmacéutico) con minimal_modules=["inventory",
    # "accounting"] — NO incluye "sales": debe bloquear.
    arrastre_sin_sales = models.CompanyPackage(
        company_id=company.id,
        package="administrative",
        status=models.PackageStatusEnum.active,
        minimal_modules=["inventory", "accounting"],
    )
    with pytest.raises(PackageNotLicensedError):
        await checker(packages={"administrative": arrastre_sin_sales})

    # Arrastre real que SÍ incluye "sales" (ej. ecommerce, módulo 23) —
    # debe pasar.
    arrastre_con_sales = models.CompanyPackage(
        company_id=company.id,
        package="administrative",
        status=models.PackageStatusEnum.active,
        minimal_modules=["inventory", "sales", "accounting"],
    )
    result = await checker(packages={"administrative": arrastre_con_sales})
    assert result is arrastre_con_sales

    # Compra directa completa del Administrativo (minimal_modules
    # None/vacío) — debe pasar para CUALQUIER minimal_module, sin importar
    # cuál, porque no es un arrastre parcial.
    compra_completa = models.CompanyPackage(
        company_id=company.id,
        package="administrative",
        status=models.PackageStatusEnum.active,
        minimal_modules=None,
    )
    result = await checker(packages={"administrative": compra_completa})
    assert result is compra_completa


# ---------------------------------------------------------------------------
# Hallazgos reales de la regresión QA externa (sep-2026): spec 8.0 marca
# 2FA y recuperación de contraseña como [core] (no [extendido]), y
# "Gestión de Usuarios [core]: perfiles, estados..." implica poder
# desactivar/reactivar — ninguna de las tres existía. Ver STATE.md
# sección 0.2 y la migración 6f6e78cc5e26 para el detalle completo.
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_set_active_idempotent_and_revokes_sessions_on_deactivate(db, auth_lookup_db, company):
    unique = uuid.uuid4().hex[:8]
    email = f"deactivate_{unique}@test.hn"

    admin = await UserService.create_user(
        db, company_id=company.id,
        payload=schemas.UserCreate(email=f"admin_{unique}@test.hn", full_name="Admin", password="password123"),
        created_by=None,
    )
    target = await UserService.create_user(
        db, company_id=company.id,
        payload=schemas.UserCreate(email=email, full_name="Target", password="password123"),
        created_by=None,
    )
    await db.commit()

    # Login real para tener una sesión (refresh token) que verificar revocada.
    tokens = await AuthService.login(
        auth_lookup_db, db,
        payload=schemas.LoginRequest(email=email, password="password123"),
        user_agent=None, ip_address=None,
    )

    # No puede autodesactivarse.
    with pytest.raises(ValidationError):
        await UserService.set_active(db, company_id=company.id, user_id=admin.id, is_active=False, actor_id=admin.id)

    updated = await UserService.set_active(
        db, company_id=company.id, user_id=target.id, is_active=False, actor_id=admin.id
    )
    assert updated.is_active is False

    # Idempotente: desactivar de nuevo no es error, no vuelve a escribir.
    updated_again = await UserService.set_active(
        db, company_id=company.id, user_id=target.id, is_active=False, actor_id=admin.id
    )
    assert updated_again.updated_at == updated.updated_at

    # La sesión activa quedó revocada — el refresh ya no funciona.
    with pytest.raises(ValidationError):
        await AuthService.refresh(auth_lookup_db, db, raw_refresh_token=tokens.refresh_token)

    # Y el login directo también falla (is_active=False en AuthService.login).
    with pytest.raises(ValidationError):
        await AuthService.login(
            auth_lookup_db, db,
            payload=schemas.LoginRequest(email=email, password="password123"),
            user_agent=None, ip_address=None,
        )

    # Reactivar: vuelve a andar.
    reactivated = await UserService.set_active(
        db, company_id=company.id, user_id=target.id, is_active=True, actor_id=admin.id
    )
    assert reactivated.is_active is True
    new_tokens = await AuthService.login(
        auth_lookup_db, db,
        payload=schemas.LoginRequest(email=email, password="password123"),
        user_agent=None, ip_address=None,
    )
    assert new_tokens.access_token


@pytest.mark.asyncio
async def test_password_reset_full_cycle_single_use(db, auth_lookup_db, company):
    unique = uuid.uuid4().hex[:8]
    email = f"pwreset_{unique}@test.hn"
    await UserService.create_user(
        db, company_id=company.id,
        payload=schemas.UserCreate(email=email, full_name="Reset Me", password="passwordViejo1"),
        created_by=None,
    )
    await db.commit()

    # Email inexistente: no debe tirar excepción (nunca revela existencia).
    await PasswordResetService.request_reset(auth_lookup_db, db, email=f"noexiste_{unique}@test.hn")

    captured: dict = {}
    original_send = PasswordResetService._send_reset_email
    PasswordResetService._send_reset_email = staticmethod(
        lambda to_email, raw_token: captured.update(email=to_email, token=raw_token)
    )
    try:
        await PasswordResetService.request_reset(auth_lookup_db, db, email=email)
    finally:
        PasswordResetService._send_reset_email = original_send

    assert captured["email"] == email
    raw_token = captured["token"]

    # Token inválido -> ValidationError genérico.
    with pytest.raises(ValidationError):
        await PasswordResetService.confirm_reset(auth_lookup_db, db, raw_token="basura", new_password="NuevaPassword2")

    await PasswordResetService.confirm_reset(auth_lookup_db, db, raw_token=raw_token, new_password="NuevaPassword2")

    # Un solo uso: reintentar el mismo token falla.
    with pytest.raises(ValidationError):
        await PasswordResetService.confirm_reset(auth_lookup_db, db, raw_token=raw_token, new_password="OtraMas3")

    # La password vieja ya no sirve, la nueva sí.
    with pytest.raises(ValidationError):
        await AuthService.login(
            auth_lookup_db, db,
            payload=schemas.LoginRequest(email=email, password="passwordViejo1"),
            user_agent=None, ip_address=None,
        )
    tokens = await AuthService.login(
        auth_lookup_db, db,
        payload=schemas.LoginRequest(email=email, password="NuevaPassword2"),
        user_agent=None, ip_address=None,
    )
    assert tokens.access_token


@pytest.mark.asyncio
async def test_2fa_setup_confirm_login_requires_code_and_disable(db, auth_lookup_db, company):
    import pyotp

    unique = uuid.uuid4().hex[:8]
    email = f"totp_{unique}@test.hn"
    user = await UserService.create_user(
        db, company_id=company.id,
        payload=schemas.UserCreate(email=email, full_name="TOTP User", password="passwordTotp1"),
        created_by=None,
    )
    await db.commit()

    # Setup: genera secreto, todavía NO habilita 2FA.
    secret, uri = await TwoFactorService.setup(db, company_id=company.id, user=user)
    assert secret
    assert "otpauth://totp/" in uri and "issuer=ERP" in uri

    # Login normal sigue funcionando — 2FA no habilitado todavía (solo setup).
    tokens = await AuthService.login(
        auth_lookup_db, db,
        payload=schemas.LoginRequest(email=email, password="passwordTotp1"),
        user_agent=None, ip_address=None,
    )
    assert tokens.access_token

    # Confirmar con código incorrecto falla.
    with pytest.raises(ValidationError):
        await TwoFactorService.confirm(db, company_id=company.id, user=user, code="000000")

    code = pyotp.TOTP(secret).now()
    await TwoFactorService.confirm(db, company_id=company.id, user=user, code=code)

    # Login sin totp_code ahora falla con requires_2fa=True en los detalles.
    with pytest.raises(ValidationError) as exc_info:
        await AuthService.login(
            auth_lookup_db, db,
            payload=schemas.LoginRequest(email=email, password="passwordTotp1"),
            user_agent=None, ip_address=None,
        )
    assert exc_info.value.details == {"requires_2fa": True}

    # Login con código correcto funciona.
    code2 = pyotp.TOTP(secret).now()
    tokens2 = await AuthService.login(
        auth_lookup_db, db,
        payload=schemas.LoginRequest(email=email, password="passwordTotp1", totp_code=code2),
        user_agent=None, ip_address=None,
    )
    assert tokens2.access_token

    # Disable con password incorrecta falla.
    with pytest.raises(ValidationError):
        await TwoFactorService.disable(db, company_id=company.id, user=user, password="incorrecta")

    await TwoFactorService.disable(db, company_id=company.id, user=user, password="passwordTotp1")

    # Login normal de nuevo, sin código.
    tokens3 = await AuthService.login(
        auth_lookup_db, db,
        payload=schemas.LoginRequest(email=email, password="passwordTotp1"),
        user_agent=None, ip_address=None,
    )
    assert tokens3.access_token
