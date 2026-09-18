from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.contacts import schemas
from app.contacts.services import ContactService
from app.core.dependencies import get_current_company_id, get_db_with_tenant_context, require_permission
from app.core.models import User

router = APIRouter(prefix="/contacts", tags=["contacts"])


@router.post("", response_model=schemas.ContactRead, status_code=201)
async def create_contact(
    payload: schemas.ContactCreate,
    company_id: int = Depends(get_current_company_id),
    db: AsyncSession = Depends(get_db_with_tenant_context),
    actor: User = Depends(require_permission("contacts:contact:create")),
) -> schemas.ContactRead:
    contact = await ContactService.create_contact(db, company_id=company_id, payload=payload, created_by=actor.id)
    return schemas.ContactRead.model_validate(contact)


@router.get("", response_model=list[schemas.ContactRead])
async def list_contacts(
    search: str | None = Query(default=None, max_length=300),
    company_id: int = Depends(get_current_company_id),
    db: AsyncSession = Depends(get_db_with_tenant_context),
    _actor: User = Depends(require_permission("contacts:contact:list")),
) -> list[schemas.ContactRead]:
    contacts = await ContactService.list_contacts(db, company_id=company_id, search=search)
    return [schemas.ContactRead.model_validate(c) for c in contacts]


@router.get("/{contact_id}", response_model=schemas.ContactRead)
async def get_contact(
    contact_id: int,
    company_id: int = Depends(get_current_company_id),
    db: AsyncSession = Depends(get_db_with_tenant_context),
    _actor: User = Depends(require_permission("contacts:contact:read")),
) -> schemas.ContactRead:
    contact = await ContactService.get_contact(db, company_id=company_id, contact_id=contact_id)
    return schemas.ContactRead.model_validate(contact)


@router.patch("/{contact_id}", response_model=schemas.ContactRead)
async def update_contact(
    contact_id: int,
    payload: schemas.ContactUpdate,
    company_id: int = Depends(get_current_company_id),
    db: AsyncSession = Depends(get_db_with_tenant_context),
    actor: User = Depends(require_permission("contacts:contact:update")),
) -> schemas.ContactRead:
    contact = await ContactService.update_contact(
        db, company_id=company_id, contact_id=contact_id, payload=payload, updated_by=actor.id
    )
    return schemas.ContactRead.model_validate(contact)


@router.patch("/{contact_id}/credit-limit", response_model=schemas.ContactRead)
async def update_contact_credit_limit(
    contact_id: int,
    payload: schemas.ContactCreditLimitUpdate,
    company_id: int = Depends(get_current_company_id),
    db: AsyncSession = Depends(get_db_with_tenant_context),
    actor: User = Depends(require_permission("contacts:contact:update_credit_limit")),
) -> schemas.ContactRead:
    """Hallazgo real de la regresión QA externa, sep-2026: `credit_limit`
    no tenía ningún endpoint de escritura. Separado del PATCH general —
    permiso propio, campo financiero sensible."""
    contact = await ContactService.update_credit_limit(
        db, company_id=company_id, contact_id=contact_id, credit_limit=payload.credit_limit, updated_by=actor.id
    )
    return schemas.ContactRead.model_validate(contact)
