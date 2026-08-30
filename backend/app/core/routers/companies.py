"""
Onboarding de compañías — DEDUCIBLE, ver app/config.py (internal_api_key):
no hay usuario todavía en la primera empresa, no puede protegerse con RBAC
normal. Placeholder temporal hasta que exista un panel de superadmin real
(fuera del alcance de core v1) — documentado explícitamente en el cierre.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Header

from app.config import settings
from app.core import schemas
from app.core.services import CompanyService
from app.database import get_db
from app.shared.exceptions import PermissionDeniedError
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/internal/companies", tags=["internal"])


def _require_internal_api_key(x_internal_api_key: str | None = Header(default=None)) -> None:
    if x_internal_api_key != settings.internal_api_key:
        raise PermissionDeniedError("X-Internal-Api-Key inválida o ausente")


@router.post("", response_model=schemas.CompanyRead, status_code=201, dependencies=[Depends(_require_internal_api_key)])
async def create_company(
    payload: schemas.CompanyCreate,
    db: AsyncSession = Depends(get_db),
) -> schemas.CompanyRead:
    company = await CompanyService.create_company(db, payload)
    return schemas.CompanyRead.model_validate(company)
