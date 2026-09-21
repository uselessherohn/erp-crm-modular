"""
Servicios de `website`. Mismo criterio anti-IDOR que el resto del proyecto:
`company_id` siempre inyectado desde el router (nunca leído del payload del
cliente) para las rutas internas; para las rutas públicas (sin JWT, ver
`routers.py`), `company_id` viene de la URL — ver AMBIGUO documentado en
`diseno_modulos_22_25_erp_crm.md` sección 2.4 sobre cómo debería resolverse
en producción (subdominio/dominio propio), no resuelto en este cierre.
"""
from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.contacts.models import Contact
from app.core.services import AuditService
from app.shared.exceptions import NotFoundError, ValidationError
from app.website import models, schemas


class PageService:
    @staticmethod
    async def create_page(
        db: AsyncSession, *, company_id: int, payload: schemas.PageCreate, created_by: int | None
    ) -> models.Page:
        page = models.Page(company_id=company_id, created_by=created_by, **payload.model_dump())
        db.add(page)
        await db.flush()

        await AuditService.log_event(
            db, company_id=company_id, event="website.page.created", entity_type="website_page",
            entity_id=page.id, user_id=created_by,
        )
        await db.commit()
        await db.refresh(page)
        return page

    @staticmethod
    async def get_page(db: AsyncSession, *, company_id: int, page_id: int) -> models.Page:
        result = await db.execute(
            select(models.Page).where(models.Page.company_id == company_id, models.Page.id == page_id)
        )
        page = result.scalar_one_or_none()
        if page is None:
            raise NotFoundError(f"Página {page_id} no encontrada")
        return page

    @staticmethod
    async def get_published_page_by_slug(db: AsyncSession, *, company_id: int, slug: str) -> models.Page:
        """Uso público (storefront) — solo páginas `published`, nunca un
        draft visible a un visitante anónimo."""
        result = await db.execute(
            select(models.Page).where(
                models.Page.company_id == company_id,
                models.Page.slug == slug,
                models.Page.status == "published",
            )
        )
        page = result.scalar_one_or_none()
        if page is None:
            raise NotFoundError(f"Página '{slug}' no encontrada o no publicada")
        return page

    @staticmethod
    async def list_pages(
        db: AsyncSession, *, company_id: int, status: str | None = None, limit: int = 50
    ) -> list[models.Page]:
        stmt = select(models.Page).where(models.Page.company_id == company_id)
        if status is not None:
            stmt = stmt.where(models.Page.status == status)
        stmt = stmt.order_by(models.Page.title).limit(limit)
        result = await db.execute(stmt)
        return list(result.scalars().all())

    @staticmethod
    async def update_page(
        db: AsyncSession, *, company_id: int, page_id: int, payload: schemas.PageUpdate, updated_by: int | None
    ) -> models.Page:
        page = await PageService.get_page(db, company_id=company_id, page_id=page_id)
        changes = payload.model_dump(exclude_unset=True)
        for field, value in changes.items():
            setattr(page, field, value)
        page.updated_by = updated_by
        await db.flush()

        await AuditService.log_event(
            db, company_id=company_id, event="website.page.updated", entity_type="website_page",
            entity_id=page.id, user_id=updated_by,
        )
        await db.commit()
        await db.refresh(page)
        return page

    @staticmethod
    async def publish_page(db: AsyncSession, *, company_id: int, page_id: int, updated_by: int | None) -> models.Page:
        page = await PageService.get_page(db, company_id=company_id, page_id=page_id)
        if page.status == "published":
            raise ValidationError(f"La página {page_id} ya está publicada")
        page.status = "published"
        page.published_at = datetime.now(UTC)
        page.updated_by = updated_by
        await db.flush()

        await AuditService.log_event(
            db, company_id=company_id, event="website.page.published", entity_type="website_page",
            entity_id=page.id, user_id=updated_by,
        )
        await db.commit()
        await db.refresh(page)
        return page

    @staticmethod
    async def unpublish_page(db: AsyncSession, *, company_id: int, page_id: int, updated_by: int | None) -> models.Page:
        page = await PageService.get_page(db, company_id=company_id, page_id=page_id)
        if page.status == "draft":
            raise ValidationError(f"La página {page_id} ya está en borrador")
        page.status = "draft"
        page.updated_by = updated_by
        await db.flush()

        await AuditService.log_event(
            db, company_id=company_id, event="website.page.unpublished", entity_type="website_page",
            entity_id=page.id, user_id=updated_by,
        )
        await db.commit()
        await db.refresh(page)
        return page


class FormSubmissionService:
    @staticmethod
    async def _find_or_create_lead_contact(
        db: AsyncSession, *, company_id: int, name: str, email: str | None, phone: str | None
    ) -> Contact:
        """DEDUCIBLE, no confirmado por Roberto: si ya existe un Contact con
        el mismo email en la compañía, se reutiliza (y se marca is_lead=true
        si no lo estaba) en vez de crear un duplicado — mismo criterio de
        "no duplicar el concepto" que DED-15 (pipeline reutiliza Contact en
        vez de un modelo Lead aparte). Sin email, siempre se crea un Contact
        nuevo (no hay forma confiable de deduplicar solo por nombre)."""
        contact: Contact | None = None
        if email:
            result = await db.execute(
                select(Contact).where(Contact.company_id == company_id, Contact.email == email)
            )
            contact = result.scalar_one_or_none()

        if contact is not None:
            if not contact.is_lead:
                contact.is_lead = True
                await db.flush()
            return contact

        contact = Contact(
            company_id=company_id,
            name=name,
            email=email,
            phone=phone,
            is_lead=True,
        )
        db.add(contact)
        await db.flush()
        return contact

    @staticmethod
    async def submit(
        db: AsyncSession, *, company_id: int, payload: schemas.FormSubmissionCreate
    ) -> models.FormSubmission:
        if payload.page_id is not None:
            # Valida pertenencia (anti-IDOR: que el page_id no sea de otra
            # compañía) — lanza NotFoundError si no aplica, mismo criterio
            # que cualquier FK validada a mano en el resto del proyecto.
            await PageService.get_page(db, company_id=company_id, page_id=payload.page_id)

        contact = await FormSubmissionService._find_or_create_lead_contact(
            db, company_id=company_id, name=payload.name, email=payload.email, phone=payload.phone
        )

        raw_payload = {
            "name": payload.name,
            "email": payload.email,
            "phone": payload.phone,
            "message": payload.message,
            **payload.extra,
        }
        submission = models.FormSubmission(
            company_id=company_id,
            page_id=payload.page_id,
            form_name=payload.form_name,
            payload=raw_payload,
            contact_id=contact.id,
        )
        db.add(submission)
        await db.flush()

        # user_id=None: envío anónimo, sin usuario autenticado (ruta
        # pública, sin JWT) — mismo patrón que cualquier evento sin actor
        # humano identificado (ej. webhooks).
        await AuditService.log_event(
            db, company_id=company_id, event="website.form_submitted", entity_type="website_form_submission",
            entity_id=submission.id, user_id=None,
        )
        await db.commit()
        await db.refresh(submission)
        return submission

    @staticmethod
    async def get_submission(db: AsyncSession, *, company_id: int, submission_id: int) -> models.FormSubmission:
        result = await db.execute(
            select(models.FormSubmission).where(
                models.FormSubmission.company_id == company_id, models.FormSubmission.id == submission_id
            )
        )
        submission = result.scalar_one_or_none()
        if submission is None:
            raise NotFoundError(f"Envío de formulario {submission_id} no encontrado")
        return submission

    @staticmethod
    async def list_submissions(
        db: AsyncSession, *, company_id: int, form_name: str | None = None, limit: int = 50
    ) -> list[models.FormSubmission]:
        stmt = select(models.FormSubmission).where(models.FormSubmission.company_id == company_id)
        if form_name is not None:
            stmt = stmt.where(models.FormSubmission.form_name == form_name)
        stmt = stmt.order_by(models.FormSubmission.created_at.desc()).limit(limit)
        result = await db.execute(stmt)
        return list(result.scalars().all())
