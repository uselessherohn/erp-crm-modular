from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import schemas
from app.core.dependencies import get_current_company_id, get_current_user, get_db, get_db_with_tenant_context
from app.core.models import User
from app.core.services import AuthService, PasswordResetService, TwoFactorService
from app.database import get_auth_lookup_db

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=schemas.TokenResponse)
async def login(
    payload: schemas.LoginRequest,
    request: Request,
    auth_lookup_db: AsyncSession = Depends(get_auth_lookup_db),
    db: AsyncSession = Depends(get_db),
) -> schemas.TokenResponse:
    return await AuthService.login(
        auth_lookup_db,
        db,
        payload=payload,
        user_agent=request.headers.get("user-agent"),
        ip_address=request.client.host if request.client else None,
    )


@router.post("/refresh", response_model=schemas.TokenResponse)
async def refresh(
    raw_refresh_token: str,
    auth_lookup_db: AsyncSession = Depends(get_auth_lookup_db),
    db: AsyncSession = Depends(get_db),
) -> schemas.TokenResponse:
    return await AuthService.refresh(auth_lookup_db, db, raw_refresh_token=raw_refresh_token)


@router.post("/logout", status_code=204)
async def logout(
    raw_refresh_token: str,
    company_id: int = Depends(get_current_company_id),
    db: AsyncSession = Depends(get_db_with_tenant_context),
    _user: User = Depends(get_current_user),
) -> None:
    await AuthService.logout(db, company_id=company_id, raw_refresh_token=raw_refresh_token)


# ---------------------------------------------------------------------------
# Recuperación de contraseña (spec 8.0 [core] — hallazgo real, sep-2026).
# Mismo patrón pre-auth que login/refresh: no hay company_id conocido
# todavía en /request (solo el email) ni en /confirm (solo el token).
# ---------------------------------------------------------------------------
@router.post("/password-reset/request", status_code=202)
async def request_password_reset(
    payload: schemas.PasswordResetRequest,
    auth_lookup_db: AsyncSession = Depends(get_auth_lookup_db),
    db: AsyncSession = Depends(get_db),
) -> dict:
    await PasswordResetService.request_reset(auth_lookup_db, db, email=payload.email)
    # Respuesta genérica sin importar si el email existe (mismo criterio
    # que login) — 202 siempre, nunca revela si la cuenta existe.
    return {"detail": "Si el email existe, se envió un link de recuperación"}


@router.post("/password-reset/confirm", status_code=204)
async def confirm_password_reset(
    payload: schemas.PasswordResetConfirm,
    auth_lookup_db: AsyncSession = Depends(get_auth_lookup_db),
    db: AsyncSession = Depends(get_db),
) -> None:
    await PasswordResetService.confirm_reset(
        auth_lookup_db, db, raw_token=payload.token, new_password=payload.new_password
    )


# ---------------------------------------------------------------------------
# 2FA / TOTP (spec 8.0 [core] — hallazgo real, sep-2026). Self-service
# únicamente (siempre sobre el usuario autenticado, nunca sobre otro
# user_id) — deshabilitar el 2FA de otra persona necesitaría su propio
# permiso administrativo, fuera de alcance de este cierre.
# ---------------------------------------------------------------------------
@router.post("/2fa/setup", response_model=schemas.TwoFactorSetupResponse)
async def setup_2fa(
    company_id: int = Depends(get_current_company_id),
    db: AsyncSession = Depends(get_db_with_tenant_context),
    user: User = Depends(get_current_user),
) -> schemas.TwoFactorSetupResponse:
    secret, provisioning_uri = await TwoFactorService.setup(db, company_id=company_id, user=user)
    return schemas.TwoFactorSetupResponse(secret=secret, provisioning_uri=provisioning_uri)


@router.post("/2fa/confirm", status_code=204)
async def confirm_2fa(
    payload: schemas.TwoFactorConfirmRequest,
    company_id: int = Depends(get_current_company_id),
    db: AsyncSession = Depends(get_db_with_tenant_context),
    user: User = Depends(get_current_user),
) -> None:
    await TwoFactorService.confirm(db, company_id=company_id, user=user, code=payload.code)


@router.post("/2fa/disable", status_code=204)
async def disable_2fa(
    payload: schemas.TwoFactorDisableRequest,
    company_id: int = Depends(get_current_company_id),
    db: AsyncSession = Depends(get_db_with_tenant_context),
    user: User = Depends(get_current_user),
) -> None:
    await TwoFactorService.disable(db, company_id=company_id, user=user, password=payload.password)
