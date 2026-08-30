from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import schemas
from app.core.dependencies import get_current_company_id, get_db_with_tenant_context, require_permission
from app.core.models import User
from app.core.services import RoleService

router = APIRouter(prefix="/roles", tags=["roles"])


@router.post("", response_model=schemas.RoleRead, status_code=201)
async def create_role(
    payload: schemas.RoleCreate,
    company_id: int = Depends(get_current_company_id),
    db: AsyncSession = Depends(get_db_with_tenant_context),
    _actor: User = Depends(require_permission("core:role:create")),
) -> schemas.RoleRead:
    role = await RoleService.create_role(db, company_id=company_id, payload=payload)
    return schemas.RoleRead.model_validate(role)


@router.get("", response_model=list[schemas.RoleRead])
async def list_roles(
    company_id: int = Depends(get_current_company_id),
    db: AsyncSession = Depends(get_db_with_tenant_context),
    _actor: User = Depends(require_permission("core:role:list")),
) -> list[schemas.RoleRead]:
    roles = await RoleService.list_roles(db, company_id=company_id)
    return [schemas.RoleRead.model_validate(r) for r in roles]
