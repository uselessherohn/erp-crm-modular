"""
Servicios de contacts. Mismo criterio anti-IDOR que core: company_id
siempre inyectado desde el router (get_current_company_id), nunca leído
del payload.
"""
from __future__ import annotations

from decimal import Decimal

from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.contacts import models, schemas
from app.core.services import AuditService
from app.shared.exceptions import ConflictError, NotFoundError


class ContactService:
    @staticmethod
    async def create_contact(
        db: AsyncSession, *, company_id: int, payload: schemas.ContactCreate, created_by: int | None
    ) -> models.Contact:
        contact = models.Contact(company_id=company_id, created_by=created_by, **payload.model_dump())
        db.add(contact)
        try:
            await db.flush()
        except IntegrityError as exc:
            await db.rollback()
            if "ux_contacts_company_email" in str(exc.orig):
                raise ConflictError(
                    f"Ya existe un contacto con el email '{payload.email}' en esta compañía"
                ) from exc
            raise

        await AuditService.log_event(
            db, company_id=company_id, event="contact.created", entity_type="contact", entity_id=contact.id, user_id=created_by
        )
        await db.commit()
        await db.refresh(contact)
        return contact

    @staticmethod
    async def get_contact(db: AsyncSession, *, company_id: int, contact_id: int) -> models.Contact:
        result = await db.execute(
            select(models.Contact).where(models.Contact.company_id == company_id, models.Contact.id == contact_id)
        )
        contact = result.scalar_one_or_none()
        if contact is None:
            raise NotFoundError(f"Contacto {contact_id} no encontrado")
        return contact

    @staticmethod
    async def list_contacts(
        db: AsyncSession, *, company_id: int, search: str | None = None, limit: int = 50
    ) -> list[models.Contact]:
        """Hallazgo real de la regresión QA externa, sep-2026: antes solo
        buscaba por `name` (trigram) — `email`/`tax_id` no eran
        buscables, confirmado con una prueba real (0 resultados buscando
        el email exacto de un contacto existente). Ahora busca en las
        tres columnas: `name` sigue usando similarity trigram (tolera
        typos), `email`/`tax_id` usan ILIKE prefijo/substring — son
        identificadores exactos, no texto libre, no tiene sentido
        aplicarles fuzzy matching."""
        if search:
            stmt = (
                select(models.Contact)
                .where(
                    models.Contact.company_id == company_id,
                    (
                        models.Contact.name.op("%")(search)
                        | models.Contact.email.ilike(f"%{search}%")
                        | models.Contact.tax_id.ilike(f"%{search}%")
                    ),
                )
                .order_by(text("similarity(name, :search) DESC"))
                .params(search=search)
                .limit(limit)
            )
        else:
            stmt = (
                select(models.Contact)
                .where(models.Contact.company_id == company_id)
                .order_by(models.Contact.name)
                .limit(limit)
            )
        result = await db.execute(stmt)
        return list(result.scalars().all())

    @staticmethod
    async def update_contact(
        db: AsyncSession, *, company_id: int, contact_id: int, payload: schemas.ContactUpdate, updated_by: int | None
    ) -> models.Contact:
        contact = await ContactService.get_contact(db, company_id=company_id, contact_id=contact_id)
        changes = payload.model_dump(exclude_unset=True)
        for field, value in changes.items():
            setattr(contact, field, value)
        contact.updated_by = updated_by
        try:
            await db.flush()
        except IntegrityError as exc:
            await db.rollback()
            if "ux_contacts_company_email" in str(exc.orig):
                raise ConflictError(
                    f"Ya existe un contacto con el email '{changes.get('email')}' en esta compañía"
                ) from exc
            raise

        await AuditService.log_event(
            db, company_id=company_id, event="contact.updated", entity_type="contact", entity_id=contact.id, user_id=updated_by
        )
        await db.commit()
        await db.refresh(contact)
        return contact

    @staticmethod
    async def update_credit_limit(
        db: AsyncSession, *, company_id: int, contact_id: int, credit_limit: Decimal | None, updated_by: int | None
    ) -> models.Contact:
        """Hallazgo real de la regresión QA externa, sep-2026: `credit_limit`
        (leído por `accounting.CreditControlService` para el Motor de
        Contención Financiera) no tenía NINGÚN endpoint que lo expusiera
        para escritura — solo lectura vía `accounting`
        `GET /credit-status/{id}`. Endpoint separado del PATCH general
        (permiso propio `contacts:contact:update_credit_limit`) porque es
        un campo financiero sensible."""
        contact = await ContactService.get_contact(db, company_id=company_id, contact_id=contact_id)
        contact.credit_limit = credit_limit
        contact.updated_by = updated_by
        await db.flush()

        await AuditService.log_event(
            db, company_id=company_id, event="contact.credit_limit_updated", entity_type="contact",
            entity_id=contact.id, user_id=updated_by,
        )
        await db.commit()
        await db.refresh(contact)
        return contact
