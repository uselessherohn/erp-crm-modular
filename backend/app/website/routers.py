from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_company_id, get_db_with_tenant_context, require_package, require_permission
from app.core.models import User
from app.website import schemas
from app.website.dependencies import ensure_web_package_active, get_public_db_context
from app.website.services import FormSubmissionService, PageService

# ---------------------------------------------------------------------------
# Panel interno (protegido — JWT + RBAC + paquete `web` contratado)
# ---------------------------------------------------------------------------
router = APIRouter(prefix="/website", tags=["website"], dependencies=[Depends(require_package("web"))])


@router.post("/pages", response_model=schemas.PageRead, status_code=201)
async def create_page(
    payload: schemas.PageCreate,
    company_id: int = Depends(get_current_company_id),
    db: AsyncSession = Depends(get_db_with_tenant_context),
    actor: User = Depends(require_permission("website:page:create")),
) -> schemas.PageRead:
    page = await PageService.create_page(db, company_id=company_id, payload=payload, created_by=actor.id)
    return schemas.PageRead.model_validate(page)


@router.get("/pages", response_model=list[schemas.PageRead])
async def list_pages(
    status: str | None = Query(default=None, pattern="^(draft|published)$"),
    company_id: int = Depends(get_current_company_id),
    db: AsyncSession = Depends(get_db_with_tenant_context),
    _actor: User = Depends(require_permission("website:page:list")),
) -> list[schemas.PageRead]:
    pages = await PageService.list_pages(db, company_id=company_id, status=status)
    return [schemas.PageRead.model_validate(p) for p in pages]


@router.get("/pages/{page_id}", response_model=schemas.PageRead)
async def get_page(
    page_id: int,
    company_id: int = Depends(get_current_company_id),
    db: AsyncSession = Depends(get_db_with_tenant_context),
    _actor: User = Depends(require_permission("website:page:read")),
) -> schemas.PageRead:
    page = await PageService.get_page(db, company_id=company_id, page_id=page_id)
    return schemas.PageRead.model_validate(page)


@router.patch("/pages/{page_id}", response_model=schemas.PageRead)
async def update_page(
    page_id: int,
    payload: schemas.PageUpdate,
    company_id: int = Depends(get_current_company_id),
    db: AsyncSession = Depends(get_db_with_tenant_context),
    actor: User = Depends(require_permission("website:page:update")),
) -> schemas.PageRead:
    page = await PageService.update_page(db, company_id=company_id, page_id=page_id, payload=payload, updated_by=actor.id)
    return schemas.PageRead.model_validate(page)


@router.post("/pages/{page_id}/publish", response_model=schemas.PageRead)
async def publish_page(
    page_id: int,
    company_id: int = Depends(get_current_company_id),
    db: AsyncSession = Depends(get_db_with_tenant_context),
    actor: User = Depends(require_permission("website:page:publish")),
) -> schemas.PageRead:
    page = await PageService.publish_page(db, company_id=company_id, page_id=page_id, updated_by=actor.id)
    return schemas.PageRead.model_validate(page)


@router.post("/pages/{page_id}/unpublish", response_model=schemas.PageRead)
async def unpublish_page(
    page_id: int,
    company_id: int = Depends(get_current_company_id),
    db: AsyncSession = Depends(get_db_with_tenant_context),
    actor: User = Depends(require_permission("website:page:unpublish")),
) -> schemas.PageRead:
    page = await PageService.unpublish_page(db, company_id=company_id, page_id=page_id, updated_by=actor.id)
    return schemas.PageRead.model_validate(page)


@router.get("/form-submissions", response_model=list[schemas.FormSubmissionRead])
async def list_form_submissions(
    form_name: str | None = Query(default=None, max_length=100),
    company_id: int = Depends(get_current_company_id),
    db: AsyncSession = Depends(get_db_with_tenant_context),
    _actor: User = Depends(require_permission("website:form_submission:list")),
) -> list[schemas.FormSubmissionRead]:
    submissions = await FormSubmissionService.list_submissions(db, company_id=company_id, form_name=form_name)
    return [schemas.FormSubmissionRead.model_validate(s) for s in submissions]


@router.get("/form-submissions/{submission_id}", response_model=schemas.FormSubmissionRead)
async def get_form_submission(
    submission_id: int,
    company_id: int = Depends(get_current_company_id),
    db: AsyncSession = Depends(get_db_with_tenant_context),
    _actor: User = Depends(require_permission("website:form_submission:read")),
) -> schemas.FormSubmissionRead:
    submission = await FormSubmissionService.get_submission(db, company_id=company_id, submission_id=submission_id)
    return schemas.FormSubmissionRead.model_validate(submission)


# ---------------------------------------------------------------------------
# Storefront público (sin JWT — spec 10: frontend separado del panel
# interno). Gating manual de paquete `web` (ver website/dependencies.py) en
# vez de `require_package`, porque ese depende de un JWT que acá no existe.
# ---------------------------------------------------------------------------
public_router = APIRouter(prefix="/public/website", tags=["website-public"])


@public_router.get("/{company_id}/pages/{slug}", response_model=schemas.PageRead)
async def get_public_page(
    company_id: int,
    slug: str,
    db: AsyncSession = Depends(get_public_db_context),
) -> schemas.PageRead:
    await ensure_web_package_active(db, company_id=company_id)
    page = await PageService.get_published_page_by_slug(db, company_id=company_id, slug=slug)
    return schemas.PageRead.model_validate(page)


@public_router.post("/{company_id}/forms", response_model=schemas.FormSubmissionRead, status_code=201)
async def submit_public_form(
    company_id: int,
    payload: schemas.FormSubmissionCreate,
    db: AsyncSession = Depends(get_public_db_context),
) -> schemas.FormSubmissionRead:
    await ensure_web_package_active(db, company_id=company_id)
    submission = await FormSubmissionService.submit(db, company_id=company_id, payload=payload)
    return schemas.FormSubmissionRead.model_validate(submission)
