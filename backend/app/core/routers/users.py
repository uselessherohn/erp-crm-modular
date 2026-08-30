from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import schemas
from app.core.dependencies import get_current_company_id, get_current_user, get_db_with_tenant_context, require_permission
from app.core.models import User
from app.core.services import UserService

router = APIRouter(prefix="/users", tags=["users"])


@router.post("", response_model=schemas.UserRead, status_code=201)
async def create_user(
    payload: schemas.UserCreate,
    company_id: int = Depends(get_current_company_id),
    db: AsyncSession = Depends(get_db_with_tenant_context),
    actor: User = Depends(require_permission("core:user:create")),
) -> schemas.UserRead:
    user = await UserService.create_user(db, company_id=company_id, payload=payload, created_by=actor.id)
    return schemas.UserRead.model_validate(user)


@router.get("", response_model=list[schemas.UserRead])
async def list_users(
    company_id: int = Depends(get_current_company_id),
    db: AsyncSession = Depends(get_db_with_tenant_context),
    _actor: User = Depends(require_permission("core:user:list")),
) -> list[schemas.UserRead]:
    users = await UserService.list_users(db, company_id=company_id)
    return [schemas.UserRead.model_validate(u) for u in users]


@router.get("/me", response_model=schemas.UserRead)
async def get_me(user: User = Depends(get_current_user)) -> schemas.UserRead:
    return schemas.UserRead.model_validate(user)


@router.get("/{user_id}", response_model=schemas.UserRead)
async def get_user(
    user_id: int,
    company_id: int = Depends(get_current_company_id),
    db: AsyncSession = Depends(get_db_with_tenant_context),
    _actor: User = Depends(require_permission("core:user:read")),
) -> schemas.UserRead:
    user = await UserService.get_user(db, company_id=company_id, user_id=user_id)
    return schemas.UserRead.model_validate(user)
