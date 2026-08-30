from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import schemas
from app.core.dependencies import get_current_company_id, get_current_user, get_db, get_db_with_tenant_context
from app.core.models import User
from app.core.services import AuthService
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
