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
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import HTTPException

from app.core import models, schemas, security
from app.config import settings
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
    ) -> models.AuditLog:
        entry = models.AuditLog(
            company_id=company_id,
            event=event,
            entity_type=entity_type,
            entity_id=entity_id,
            user_id=user_id,
            correlation_id=correlation_id or str(uuid.uuid4()),
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

        now = datetime.now(timezone.utc)
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
        now = datetime.now(timezone.utc)

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
            session.revoked_at = datetime.now(timezone.utc)
            await db.commit()


# ---------------------------------------------------------------------------
# Idempotencia (spec sección 7, mecanismo concreto nuevo en v10.3, TTL por
# dominio y "solo 2xx/4xx definitivo" corregidos en v10.4) — TODO-03: primer
# consumidor real es `accounting` (facturación, pagos, notas), pero vive acá
# en `core` para que cualquier módulo futuro (medical, pharmacy) lo reutilice
# sin reinventar el mecanismo.
# ---------------------------------------------------------------------------
class IdempotencyService:
    _TTL_HOURS_BY_DOMAIN = {
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
        if existing.expires_at < datetime.now(timezone.utc):
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
                expires_at=datetime.now(timezone.utc) + timedelta(hours=ttl_hours),
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
