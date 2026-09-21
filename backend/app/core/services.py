"""
Servicios del módulo core. Los routers no hacen commit directamente
(spec sección 3) — los servicios controlan la lógica y las transacciones.
Todo método que lee/escribe datos de negocio recibe `company_id` inyectado
desde el router (nunca del payload) y lo aplica explícitamente en el filtro
(regla dura anti-IDOR, spec sección 5) — además de la capa RLS.
"""
from __future__ import annotations

import hashlib
import json
import uuid
from datetime import UTC, datetime, timedelta
from typing import ClassVar

import pyotp
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core import models, schemas, security
from app.shared.exceptions import ConflictError, DomainError, IdempotencyConflictError, NotFoundError, ValidationError


# ---------------------------------------------------------------------------
# Auditoría — audit mínimo [core] (spec 8.0)
# ---------------------------------------------------------------------------
class DocumentNumberingService:
    """Numeración atómica de documentos (spec sección 5/Concurrencia).
    Reutilizable por purchasing, sales, accounting y cualquier módulo
    futuro con documentos numerados — nadie reinventa esto."""

    @staticmethod
    async def next_number(db: AsyncSession, *, company_id: int, doc_type: str, prefix: str, year: int) -> str:
        # UPSERT a 0 (garantiza la fila) + SELECT FOR UPDATE + incremento —
        # mismo patrón que StockService._apply_delta (inventory), mismo
        # motivo: serializar por fila (company_id, doc_type, year), no por
        # tabla completa, y sin la carrera de "dos inserts concurrentes de
        # la primera fila".
        from sqlalchemy.dialects.postgresql import insert as pg_insert

        upsert_stmt = (
            pg_insert(models.DocumentCounter)
            .values(company_id=company_id, doc_type=doc_type, year=year, current_number=0)
            .on_conflict_do_nothing(index_elements=["company_id", "doc_type", "year"])
        )
        await db.execute(upsert_stmt)

        result = await db.execute(
            select(models.DocumentCounter)
            .where(
                models.DocumentCounter.company_id == company_id,
                models.DocumentCounter.doc_type == doc_type,
                models.DocumentCounter.year == year,
            )
            .with_for_update()
        )
        counter = result.scalar_one()
        counter.current_number += 1
        await db.flush()

        return f"{prefix}-{year}-{counter.current_number:06d}"


class AuditService:
    @staticmethod
    async def log_event(
        db: AsyncSession,
        *,
        company_id: int,
        event: str,
        entity_type: str,
        entity_id: int,
        user_id: int | None,
        correlation_id: str | None = None,
        changes: dict | None = None,
    ) -> models.AuditLog:
        entry = models.AuditLog(
            company_id=company_id,
            event=event,
            entity_type=entity_type,
            entity_id=entity_id,
            user_id=user_id,
            correlation_id=correlation_id or str(uuid.uuid4()),
            changes=changes,
        )
        db.add(entry)
        await db.flush()
        return entry


# ---------------------------------------------------------------------------
# Empresas
# ---------------------------------------------------------------------------
class CompanyService:
    @staticmethod
    async def create_company(db: AsyncSession, payload: schemas.CompanyCreate) -> models.Company:
        # Única operación del sistema sin company_id previo — es la que lo crea.
        company = models.Company(**payload.model_dump())
        db.add(company)
        await db.flush()
        await db.commit()
        await db.refresh(company)
        return company


# ---------------------------------------------------------------------------
# Usuarios
# ---------------------------------------------------------------------------
class UserService:
    @staticmethod
    async def create_user(
        db: AsyncSession, *, company_id: int, payload: schemas.UserCreate, created_by: int | None
    ) -> models.User:
        existing = await db.execute(
            select(models.User).where(
                models.User.company_id == company_id, models.User.email == payload.email
            )
        )
        if existing.scalar_one_or_none() is not None:
            raise ConflictError(f"Ya existe un usuario con email '{payload.email}' en esta compañía")

        user = models.User(
            company_id=company_id,
            email=payload.email,
            full_name=payload.full_name,
            locale=payload.locale,
            timezone=payload.timezone,
            hashed_password=security.hash_password(payload.password),
            created_by=created_by,
        )
        db.add(user)
        await db.flush()

        if payload.role_ids:
            roles_result = await db.execute(
                select(models.Role).where(
                    models.Role.company_id == company_id, models.Role.id.in_(payload.role_ids)
                )
            )
            found_roles = roles_result.scalars().all()
            if len(found_roles) != len(set(payload.role_ids)):
                raise ValidationError("Uno o más role_ids no existen en esta compañía")
            for role in found_roles:
                db.add(models.UserRole(user_id=user.id, role_id=role.id))

        await AuditService.log_event(
            db,
            company_id=company_id,
            event="user.created",
            entity_type="user",
            entity_id=user.id,
            user_id=created_by,
        )
        await db.commit()
        await db.refresh(user)
        return user

    @staticmethod
    async def get_user(db: AsyncSession, *, company_id: int, user_id: int) -> models.User:
        result = await db.execute(
            select(models.User).where(models.User.company_id == company_id, models.User.id == user_id)
        )
        user = result.scalar_one_or_none()
        if user is None:
            raise NotFoundError(f"Usuario {user_id} no encontrado")
        return user

    @staticmethod
    async def list_users(db: AsyncSession, *, company_id: int) -> list[models.User]:
        result = await db.execute(select(models.User).where(models.User.company_id == company_id))
        return list(result.scalars().all())

    @staticmethod
    async def set_active(
        db: AsyncSession, *, company_id: int, user_id: int, is_active: bool, actor_id: int
    ) -> models.User:
        """Activar/desactivar usuario (spec 8.0, "Gestión de Usuarios
        [core]: perfiles, estados...") — hallazgo real de la regresión QA
        externa, sep-2026: no existía ninguna forma de hacer esto.

        Idempotente (catálogo de regresión, sección 3.3 "transiciones de
        estado inválidas"): desactivar un usuario ya inactivo, o reactivar
        uno ya activo, no es error — devuelve el estado actual sin
        volver a escribir ni auditar de nuevo.

        Al desactivar: revoca todas las sesiones activas (refresh tokens)
        del usuario, de inmediato — no espera a que expiren. El access
        token JWT ya emitido sigue siendo válido en tránsito, pero
        get_current_user vuelve a chequear is_active en cada request
        (app/core/dependencies.py), así que la siguiente petición del
        usuario con ese token también falla — la ventana de exposición es
        como máximo el tiempo de vida restante de un único access token
        (jwt_access_token_expire_minutes), nunca indefinida vía refresh."""
        user = await UserService.get_user(db, company_id=company_id, user_id=user_id)

        if user.is_active == is_active:
            return user  # no-op idempotente — sin doble escritura ni doble auditoría

        if not is_active and user_id == actor_id:
            raise ValidationError("No podés desactivar tu propio usuario")

        user.is_active = is_active
        user.updated_by = actor_id

        if not is_active:
            from sqlalchemy import update as _update

            await db.execute(
                _update(models.UserSession)
                .where(
                    models.UserSession.user_id == user_id,
                    models.UserSession.revoked_at.is_(None),
                )
                .values(revoked_at=datetime.now(UTC))
            )

        await AuditService.log_event(
            db,
            company_id=company_id,
            event="user.activated" if is_active else "user.deactivated",
            entity_type="user",
            entity_id=user.id,
            user_id=actor_id,
        )
        await db.commit()
        await db.refresh(user)
        return user


# ---------------------------------------------------------------------------
# Roles
# ---------------------------------------------------------------------------
class RoleService:
    @staticmethod
    async def create_role(
        db: AsyncSession, *, company_id: int, payload: schemas.RoleCreate
    ) -> models.Role:
        existing = await db.execute(
            select(models.Role).where(models.Role.company_id == company_id, models.Role.name == payload.name)
        )
        if existing.scalar_one_or_none() is not None:
            raise ConflictError(f"Ya existe un rol '{payload.name}' en esta compañía")

        role = models.Role(company_id=company_id, name=payload.name, description=payload.description)
        db.add(role)
        await db.flush()

        if payload.permission_ids:
            perms_result = await db.execute(
                select(models.Permission).where(models.Permission.id.in_(payload.permission_ids))
            )
            found = perms_result.scalars().all()
            if len(found) != len(set(payload.permission_ids)):
                raise ValidationError("Uno o más permission_ids no existen")
            for perm in found:
                db.add(models.RolePermission(role_id=role.id, permission_id=perm.id))

        await db.commit()
        await db.refresh(role)
        return role

    @staticmethod
    async def list_roles(db: AsyncSession, *, company_id: int) -> list[models.Role]:
        result = await db.execute(select(models.Role).where(models.Role.company_id == company_id))
        return list(result.scalars().all())


# ---------------------------------------------------------------------------
# Autenticación (spec 8.0 — login, sesiones activas, bloqueo por intentos)
# ---------------------------------------------------------------------------
class AuthService:
    MAX_FAILED_ATTEMPTS = 5
    LOCKOUT_MINUTES = 15

    @staticmethod
    async def login(
        auth_lookup_db: AsyncSession,
        db: AsyncSession,
        *,
        payload: schemas.LoginRequest,
        user_agent: str | None,
        ip_address: str | None,
    ) -> schemas.TokenResponse:
        """AMBIGUO — decisión DEDUCIBLE registrada (spec no resuelve
        resolución de tenant pre-auth): `auth_lookup_db` corre bajo el rol
        `erp_auth_lookup` (BYPASSRLS, solo SELECT sobre columnas concretas
        de `users`) — el único punto del sistema donde se busca un usuario
        SIN conocer su `company_id` de antemano. Una vez identificado el
        `company_id`, todo lo demás (actualizar intentos fallidos, crear
        sesión, escribir audit) pasa por `db`, con RLS normal vía
        set_config(). Nunca se usa `auth_lookup_db` para escribir."""
        result = await auth_lookup_db.execute(
            select(models.User.id, models.User.company_id).where(models.User.email == payload.email)
        )
        row = result.first()

        # Nunca revelar si el email existe o no — mismo mensaje en ambos casos.
        invalid_credentials = ValidationError("Credenciales inválidas")

        if row is None:
            raise invalid_credentials

        user_id, company_id = row

        # Fija el contexto RLS en la sesión normal ANTES de cualquier lectura
        # o escritura sobre ella — recién ahora que conocemos company_id.
        from sqlalchemy import text as _text

        await db.execute(
            _text("SELECT set_config('app.current_company_id', :cid, false)"),
            {"cid": str(company_id)},
        )

        # Re-consulta por `db` (sesión con RLS ya fijado): el objeto de
        # `auth_lookup_db` pertenece a otro engine/sesión — mutarlo y hacer
        # commit() en `db` no persistiría nada (bug real detectado al
        # escribir esto, corregido acá en vez de dejarlo pasar).
        result = await db.execute(select(models.User).where(models.User.id == user_id))
        user = result.scalar_one_or_none()
        if user is None or not user.is_active:
            raise invalid_credentials

        now = datetime.now(UTC)
        if user.locked_until is not None and user.locked_until > now:
            raise ValidationError(
                f"Cuenta bloqueada por intentos fallidos hasta {user.locked_until.isoformat()}"
            )

        if not security.verify_password(payload.password, user.hashed_password):
            user.failed_login_attempts += 1
            if user.failed_login_attempts >= AuthService.MAX_FAILED_ATTEMPTS:
                user.locked_until = now + timedelta(minutes=AuthService.LOCKOUT_MINUTES)
                user.failed_login_attempts = 0
            await db.commit()
            raise invalid_credentials

        user.failed_login_attempts = 0
        user.locked_until = None

        if user.totp_enabled:
            if not payload.totp_code:
                await db.commit()
                raise ValidationError(
                    "Este usuario tiene 2FA habilitado — falta el código TOTP (totp_code)",
                    details={"requires_2fa": True},
                )
            # DEDUCIBLE: un código TOTP incorrecto no incrementa
            # failed_login_attempts (ese contador es específico de
            # contraseña, ya consumido arriba). Rate-limiting específico
            # para fuerza bruta de TOTP queda fuera de este cierre — el
            # código de 6 dígitos + ventana de 30s ya limita naturalmente
            # el espacio de intentos por segundo, pero no hay un tope
            # explícito de intentos como sí existe para la contraseña.
            if not await TwoFactorService._verify_code(db, user=user, code=payload.totp_code):
                await db.commit()
                raise invalid_credentials

        access_token = security.create_access_token(user_id=user.id, company_id=company_id)
        raw_refresh, refresh_hash = security.generate_refresh_token()

        session = models.UserSession(
            company_id=company_id,
            user_id=user.id,
            refresh_token_hash=refresh_hash,
            user_agent=user_agent,
            ip_address=ip_address,
            expires_at=now + timedelta(days=settings.jwt_refresh_token_expire_days),
        )
        db.add(session)

        await AuditService.log_event(
            db, company_id=company_id, event="auth.login", entity_type="user", entity_id=user.id, user_id=user.id
        )
        await db.commit()

        return schemas.TokenResponse(access_token=access_token, refresh_token=raw_refresh)

    @staticmethod
    async def refresh(
        auth_lookup_db: AsyncSession, db: AsyncSession, *, raw_refresh_token: str
    ) -> schemas.TokenResponse:
        """Mismo patrón que login (ver docstring ahí): al momento de refrescar,
        el access token ya expiró, así que tampoco hay company_id disponible
        vía get_current_user. refresh_token_hash es único globalmente
        (UserSession.refresh_token_hash, unique=True) — se resuelve
        company_id desde ahí vía el rol de solo lectura BYPASSRLS, y recién
        entonces se fija el contexto RLS para todo lo demás."""
        token_hash = security.hash_refresh_token(raw_refresh_token)
        now = datetime.now(UTC)

        lookup_result = await auth_lookup_db.execute(
            select(models.UserSession.id, models.UserSession.company_id).where(
                models.UserSession.refresh_token_hash == token_hash
            )
        )
        lookup_row = lookup_result.first()
        if lookup_row is None:
            raise ValidationError("Refresh token inválido, revocado o expirado")

        session_id, company_id = lookup_row

        from sqlalchemy import text as _text

        await db.execute(
            _text("SELECT set_config('app.current_company_id', :cid, false)"),
            {"cid": str(company_id)},
        )

        result = await db.execute(select(models.UserSession).where(models.UserSession.id == session_id))
        session = result.scalar_one_or_none()
        if session is None or session.revoked_at is not None or session.expires_at < now:
            raise ValidationError("Refresh token inválido, revocado o expirado")

        # Hallazgo real de la regresión QA externa, sep-2026: refresh() no
        # chequeaba is_active del usuario — un usuario desactivado con una
        # sesión todavía no revocada podía seguir renovando su access
        # token indefinidamente. UserService.set_active ya revoca las
        # sesiones activas al desactivar (defensa primaria); este chequeo
        # es la segunda capa, por si alguna sesión quedó sin revocar por
        # cualquier otro camino.
        user_result = await db.execute(select(models.User.is_active).where(models.User.id == session.user_id))
        user_is_active = user_result.scalar_one_or_none()
        if not user_is_active:
            raise ValidationError("Refresh token inválido, revocado o expirado")

        # Rotación: se revoca el usado y se emite uno nuevo.
        session.revoked_at = now
        access_token = security.create_access_token(user_id=session.user_id, company_id=company_id)
        raw_refresh, refresh_hash = security.generate_refresh_token()

        new_session = models.UserSession(
            company_id=company_id,
            user_id=session.user_id,
            refresh_token_hash=refresh_hash,
            user_agent=session.user_agent,
            ip_address=session.ip_address,
            expires_at=now + timedelta(days=settings.jwt_refresh_token_expire_days),
        )
        db.add(new_session)
        await db.commit()

        return schemas.TokenResponse(access_token=access_token, refresh_token=raw_refresh)

    @staticmethod
    async def logout(db: AsyncSession, *, company_id: int, raw_refresh_token: str) -> None:
        token_hash = security.hash_refresh_token(raw_refresh_token)
        result = await db.execute(
            select(models.UserSession).where(
                models.UserSession.company_id == company_id,
                models.UserSession.refresh_token_hash == token_hash,
            )
        )
        session = result.scalar_one_or_none()
        if session is not None:
            session.revoked_at = datetime.now(UTC)
            await db.commit()


# ---------------------------------------------------------------------------
# Recuperación de contraseña (spec 8.0 [core] — hallazgo real de la
# regresión QA externa, sep-2026: nunca se había construido pese a estar
# marcado [core]). Mismo patrón cross-tenant que AuthService.login/refresh:
# el flujo empieza sin conocer company_id, se resuelve vía erp_auth_lookup
# (BYPASSRLS, columnas concretas), y solo entonces se fija el contexto RLS.
# ---------------------------------------------------------------------------
class PasswordResetService:
    @staticmethod
    async def request_reset(
        auth_lookup_db: AsyncSession, db: AsyncSession, *, email: str
    ) -> None:
        """Nunca revela si el email existe (mismo criterio que login) — la
        respuesta al cliente es idéntica exista o no la cuenta; solo
        cambia si efectivamente se genera un token y se "envía" el email
        (en este entorno, un log — ver _send_reset_email)."""
        result = await auth_lookup_db.execute(
            select(models.User.id, models.User.company_id, models.User.is_active).where(
                models.User.email == email
            )
        )
        row = result.first()
        if row is None or not row.is_active:
            return  # silencioso — no revela existencia del email

        user_id, company_id, _ = row

        from sqlalchemy import text as _text

        await db.execute(
            _text("SELECT set_config('app.current_company_id', :cid, false)"),
            {"cid": str(company_id)},
        )

        raw_token, token_hash = security.generate_password_reset_token()
        now = datetime.now(UTC)
        reset_token = models.PasswordResetToken(
            company_id=company_id,
            user_id=user_id,
            token_hash=token_hash,
            expires_at=now + timedelta(minutes=settings.password_reset_token_expire_minutes),
        )
        db.add(reset_token)

        await AuditService.log_event(
            db, company_id=company_id, event="auth.password_reset_requested",
            entity_type="user", entity_id=user_id, user_id=user_id,
        )
        await db.commit()

        PasswordResetService._send_reset_email(email, raw_token)

    @staticmethod
    def _send_reset_email(email: str, raw_token: str) -> None:
        """DEDUCIBLE (mismo tipo de limitación que EmailSender en
        notifications — sin acceso de red a un proveedor real de email en
        este entorno): se loguea, no se envía. `core` no puede importar
        `app.notifications` (violaría el grafo de dependencias — core no
        depende de nada, notifications depende de core, no al revés), así
        que este stub es local, no una reutilización de
        notifications.EmailSender."""
        import logging

        logging.getLogger("core.auth.password_reset").info(
            "EMAIL (dev, no enviado) to=%s subject='Recuperación de contraseña' token=%s",
            email, raw_token,
        )

    @staticmethod
    async def confirm_reset(
        auth_lookup_db: AsyncSession, db: AsyncSession, *, raw_token: str, new_password: str
    ) -> None:
        token_hash = security.hash_password_reset_token(raw_token)
        now = datetime.now(UTC)

        lookup_result = await auth_lookup_db.execute(
            select(
                models.PasswordResetToken.id,
                models.PasswordResetToken.company_id,
                models.PasswordResetToken.user_id,
                models.PasswordResetToken.expires_at,
                models.PasswordResetToken.used_at,
            ).where(models.PasswordResetToken.token_hash == token_hash)
        )
        lookup_row = lookup_result.first()
        generic_error = ValidationError("Token de recuperación inválido, expirado o ya usado")
        if lookup_row is None:
            raise generic_error

        token_id, company_id, user_id, expires_at, used_at = lookup_row
        if used_at is not None or expires_at < now:
            raise generic_error

        from sqlalchemy import text as _text

        await db.execute(
            _text("SELECT set_config('app.current_company_id', :cid, false)"),
            {"cid": str(company_id)},
        )

        token_result = await db.execute(
            select(models.PasswordResetToken).where(models.PasswordResetToken.id == token_id)
        )
        token = token_result.scalar_one_or_none()
        if token is None or token.used_at is not None or token.expires_at < now:
            raise generic_error

        user_result = await db.execute(select(models.User).where(models.User.id == user_id))
        user = user_result.scalar_one_or_none()
        if user is None:
            raise generic_error

        user.hashed_password = security.hash_password(new_password)
        token.used_at = now

        # Un reset de contraseña invalida toda sesión existente — mismo
        # criterio que desactivar un usuario (UserService.set_active):
        # si alguien más tenía acceso con la contraseña vieja, este es el
        # punto donde se corta.
        from sqlalchemy import update as _update

        await db.execute(
            _update(models.UserSession)
            .where(models.UserSession.user_id == user_id, models.UserSession.revoked_at.is_(None))
            .values(revoked_at=now)
        )

        await AuditService.log_event(
            db, company_id=company_id, event="auth.password_reset_confirmed",
            entity_type="user", entity_id=user_id, user_id=user_id,
        )
        await db.commit()


# ---------------------------------------------------------------------------
# 2FA / TOTP (spec 8.0 [core] — hallazgo real de la regresión QA externa,
# sep-2026: nunca se había construido pese a estar marcado [core]).
# Secreto cifrado en reposo vía pgcrypto — mismo patrón que medical (ver
# app/medical/services.py _encrypt/_decrypt_col).
# ---------------------------------------------------------------------------
class TwoFactorService:
    @staticmethod
    def _encrypt_secret(secret: str):
        from sqlalchemy import func

        return func.pgp_sym_encrypt(secret, settings.pgcrypto_key)

    @staticmethod
    async def _get_decrypted_secret(db: AsyncSession, *, user_id: int) -> str | None:
        from sqlalchemy import func

        result = await db.execute(
            select(func.pgp_sym_decrypt(models.User.totp_secret_encrypted, settings.pgcrypto_key)).where(
                models.User.id == user_id, models.User.totp_secret_encrypted.is_not(None)
            )
        )
        row = result.first()
        return row[0] if row is not None else None

    @staticmethod
    async def _verify_code(db: AsyncSession, *, user: models.User, code: str) -> bool:
        secret = await TwoFactorService._get_decrypted_secret(db, user_id=user.id)
        if secret is None:
            return False
        return pyotp.TOTP(secret).verify(code, valid_window=1)

    @staticmethod
    async def setup(db: AsyncSession, *, company_id: int, user: models.User) -> tuple[str, str]:
        """Genera un secreto nuevo y lo guarda cifrado, todavía sin
        habilitar (totp_enabled sigue false hasta `confirm`) — evita que
        un usuario quede bloqueado de su propia cuenta por guardar un
        secreto que nunca llegó a confirmar que puede leer correctamente
        en su app autenticadora."""
        secret = pyotp.random_base32()
        provisioning_uri = pyotp.TOTP(secret).provisioning_uri(
            name=user.email, issuer_name=settings.totp_issuer_name
        )

        from sqlalchemy import update as _update

        await db.execute(
            _update(models.User)
            .where(models.User.id == user.id)
            .values(totp_secret_encrypted=TwoFactorService._encrypt_secret(secret), totp_enabled=False)
        )
        await db.commit()
        return secret, provisioning_uri

    @staticmethod
    async def confirm(db: AsyncSession, *, company_id: int, user: models.User, code: str) -> None:
        secret = await TwoFactorService._get_decrypted_secret(db, user_id=user.id)
        if secret is None:
            raise ValidationError("No hay un setup de 2FA pendiente — llamá a /auth/2fa/setup primero")
        if not pyotp.TOTP(secret).verify(code, valid_window=1):
            raise ValidationError("Código TOTP inválido")

        from sqlalchemy import update as _update

        await db.execute(_update(models.User).where(models.User.id == user.id).values(totp_enabled=True))
        await AuditService.log_event(
            db, company_id=company_id, event="auth.2fa_enabled", entity_type="user",
            entity_id=user.id, user_id=user.id,
        )
        await db.commit()

    @staticmethod
    async def disable(db: AsyncSession, *, company_id: int, user: models.User, password: str) -> None:
        """Requiere re-confirmar la contraseña — deshabilitar 2FA reduce
        la seguridad de la cuenta, no debería ser posible solo con un
        access token robado de una sesión ya abierta."""
        if not security.verify_password(password, user.hashed_password):
            raise ValidationError("Contraseña incorrecta")

        from sqlalchemy import update as _update

        await db.execute(
            _update(models.User)
            .where(models.User.id == user.id)
            .values(totp_enabled=False, totp_secret_encrypted=None)
        )
        await AuditService.log_event(
            db, company_id=company_id, event="auth.2fa_disabled", entity_type="user",
            entity_id=user.id, user_id=user.id,
        )
        await db.commit()



# ---------------------------------------------------------------------------
# Idempotencia (spec sección 7, mecanismo concreto nuevo en v10.3, TTL por
# dominio y "solo 2xx/4xx definitivo" corregidos en v10.4) — TODO-03: primer
# consumidor real es `accounting` (facturación, pagos, notas), pero vive acá
# en `core` para que cualquier módulo futuro (medical, pharmacy) lo reutilice
# sin reinventar el mecanismo.
# ---------------------------------------------------------------------------
class IdempotencyService:
    _TTL_HOURS_BY_DOMAIN: ClassVar[dict[str, str]] = {
        "sales": "idempotency_ttl_hours_sales",
        "accounting": "idempotency_ttl_hours_accounting",
        "medical_billing": "idempotency_ttl_hours_medical_billing",
        "pharmacy": "idempotency_ttl_hours_pharmacy",
    }

    @staticmethod
    def hash_payload(payload: dict) -> str:
        # sort_keys=True + default=str: determinístico sin importar el
        # orden de construcción del dict ni tipos no serializables nativos
        # (Decimal, date) que sí importan para detectar payloads distintos.
        canonical = json.dumps(payload, sort_keys=True, default=str)
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    @staticmethod
    async def get_replay(
        db: AsyncSession, *, company_id: int, idempotency_key: str, endpoint: str, request_hash: str
    ) -> models.IdempotencyKey | None:
        """Se llama ANTES de ejecutar la lógica de negocio. Devuelve la fila
        persistida si esta es una repetición legítima (mismo hash, dentro de
        TTL) — el caller debe devolver `response_snapshot`/`response_status_code`
        tal cual, sin re-ejecutar nada. Lanza `IdempotencyConflictError` (409)
        si la misma clave se reusa con un payload distinto. Devuelve `None`
        si no hay colisión (clave nueva, o fila expirada — una clave vencida
        se trata como si no existiera, permitiendo reintentar desde cero)."""
        result = await db.execute(
            select(models.IdempotencyKey).where(
                models.IdempotencyKey.company_id == company_id,
                models.IdempotencyKey.idempotency_key == idempotency_key,
                models.IdempotencyKey.endpoint == endpoint,
            )
        )
        existing = result.scalar_one_or_none()
        if existing is None:
            return None
        if existing.expires_at < datetime.now(UTC):
            return None
        if existing.request_hash != request_hash:
            raise IdempotencyConflictError(
                f"La clave de idempotencia '{idempotency_key}' ya se usó con un payload distinto"
            )
        return existing

    @staticmethod
    async def persist_response(
        db: AsyncSession,
        *,
        company_id: int,
        idempotency_key: str,
        endpoint: str,
        request_hash: str,
        domain: str,
        response_status_code: int,
        response_body: dict,
    ) -> None:
        """Se llama DESPUÉS de ejecutar la lógica de negocio. Solo persiste
        ante 2xx o 4xx definitivo (spec v10.4) — nunca ante 5xx, para que un
        reintento legítimo tras una falla transitoria no quede "congelado"
        con el mismo error de servidor. El caller es responsable de no
        invocar este método si la respuesta fue 5xx."""
        if response_status_code >= 500:
            return
        ttl_hours = getattr(settings, IdempotencyService._TTL_HOURS_BY_DOMAIN[domain])
        db.add(
            models.IdempotencyKey(
                company_id=company_id,
                idempotency_key=idempotency_key,
                endpoint=endpoint,
                request_hash=request_hash,
                response_snapshot=response_body,
                response_status_code=response_status_code,
                expires_at=datetime.now(UTC) + timedelta(hours=ttl_hours),
            )
        )
        await db.flush()

    @staticmethod
    async def run_command(
        db: AsyncSession,
        *,
        company_id: int,
        idempotency_key: str | None,
        endpoint: str,
        payload_dict: dict,
        domain: str,
        success_status_code: int,
        command,
    ):
        """Envoltura reutilizable por cualquier router que exponga un
        comando mutable con soporte de idempotencia (spec 7) — evita que
        cada endpoint reimplemente el flujo check→ejecutar→persistir.
        `command` es un callable async sin argumentos que ejecuta la
        lógica de negocio y devuelve el modelo Pydantic de respuesta ya
        construido (o cualquier valor serializable con `.model_dump`).
        Sin `Idempotency-Key`, se ejecuta el comando tal cual, sin
        persistir nada — la idempotencia es opt-in por request, no
        obligatoria."""
        if idempotency_key is None:
            return await command()

        request_hash = IdempotencyService.hash_payload(payload_dict)
        replay = await IdempotencyService.get_replay(
            db, company_id=company_id, idempotency_key=idempotency_key, endpoint=endpoint, request_hash=request_hash
        )
        if replay is not None:
            if replay.response_status_code >= 400:
                raise HTTPException(status_code=replay.response_status_code, detail=replay.response_snapshot)
            return replay.response_snapshot

        try:
            result = await command()
        except DomainError as exc:
            # La sesión puede tener cambios a medio aplicar si el comando
            # falló después de algún db.add()/flush() — se descartan antes
            # de persistir el registro de idempotencia, para no dejar la
            # sesión en un estado inconsistente en el siguiente uso.
            await db.rollback()
            await IdempotencyService.persist_response(
                db,
                company_id=company_id,
                idempotency_key=idempotency_key,
                endpoint=endpoint,
                request_hash=request_hash,
                domain=domain,
                response_status_code=exc.status_code,
                response_body={"error": {"code": exc.error_code, "message": exc.message, "details": exc.details}},
            )
            await db.commit()
            raise

        response_body = result.model_dump(mode="json") if hasattr(result, "model_dump") else result
        await IdempotencyService.persist_response(
            db,
            company_id=company_id,
            idempotency_key=idempotency_key,
            endpoint=endpoint,
            request_hash=request_hash,
            domain=domain,
            response_status_code=success_status_code,
            response_body=response_body,
        )
        await db.commit()
        return result


# ---------------------------------------------------------------------------
# Adjuntos genéricos (spec 8.2, "carga de resultados vía attachments") —
# primer consumidor real: `medical` (laboratorio, módulo 11). Interfaz de
# dominio reutilizable por cualquier módulo, con `entity_type`/`entity_id`
# genérico (mismo patrón polimórfico que `audit`). DEDUCIBLE: el propio
# router que expone la subida NO es genérico (no hay `POST /attachments`
# universal que acepte cualquier `entity_type` de cualquier módulo sin
# control) — cada módulo consumidor expone su propio endpoint anidado
# (ej. `POST /medical/lab-order-tests/{id}/attachments`) que llama a este
# servicio con un `entity_type` fijo que él mismo controla, después de
# verificar el RBAC sobre el recurso real. Evita la superficie de un
# endpoint que permite adjuntar archivos a un `entity_id` de un módulo
# ajeno sin pasar por su propio control de acceso.
# ---------------------------------------------------------------------------
class AttachmentService:
    @staticmethod
    async def store(
        db: AsyncSession, *, company_id: int, entity_type: str, entity_id: int,
        filename: str, mime_type: str, content: bytes, uploaded_by: int,
    ) -> models.Attachment:
        import os
        from pathlib import Path

        storage_root = Path(settings.attachment_storage_root) / str(company_id) / entity_type
        storage_root.mkdir(parents=True, exist_ok=True)
        stored_filename = f"{uuid.uuid4().hex}_{filename}"
        storage_path = storage_root / stored_filename
        storage_path.write_bytes(content)

        attachment = models.Attachment(
            company_id=company_id, entity_type=entity_type, entity_id=entity_id,
            filename=filename, mime_type=mime_type, storage_path=os.fspath(storage_path),
            uploaded_by=uploaded_by,
        )
        db.add(attachment)
        await db.commit()
        await db.refresh(attachment)
        return attachment

    @staticmethod
    async def list_for_entity(db: AsyncSession, *, company_id: int, entity_type: str, entity_id: int) -> list[models.Attachment]:
        result = await db.execute(
            select(models.Attachment).where(
                models.Attachment.company_id == company_id,
                models.Attachment.entity_type == entity_type,
                models.Attachment.entity_id == entity_id,
            ).order_by(models.Attachment.created_at)
        )
        return list(result.scalars().all())

    @staticmethod
    async def get(db: AsyncSession, *, company_id: int, attachment_id: int) -> models.Attachment | None:
        result = await db.execute(
            select(models.Attachment).where(
                models.Attachment.company_id == company_id, models.Attachment.id == attachment_id
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    def read_bytes(attachment: models.Attachment) -> bytes:
        from pathlib import Path

        return Path(attachment.storage_path).read_bytes()
