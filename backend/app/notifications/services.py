"""
Servicios de notifications. Ver docstring de `models.py` para las
decisiones DEDUCIBLE (DED-27, DED-28, DED-29).
"""
from __future__ import annotations

import abc
import logging
import string

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.notifications import models, schemas
from app.shared.exceptions import ConflictError, NotFoundError, ValidationError

logger = logging.getLogger("notifications.email")


# ---------------------------------------------------------------------------
# Motor de Correos (DED-27) — interfaz real, implementación de desarrollo.
# ---------------------------------------------------------------------------
class EmailSender(abc.ABC):
    @abc.abstractmethod
    async def send(self, *, to_email: str, subject: str, body: str) -> str:
        """Devuelve el `email_status` resultante ('sent' | 'logged_only')."""
        raise NotImplementedError


class LoggingEmailSender(EmailSender):
    """Implementación de desarrollo — el sandbox de este proyecto no tiene
    salida de red hacia ningún proveedor SMTP/API de correo (DED-27). En
    producción, esta clase se reemplaza por una implementación real
    (ej. SES/SendGrid) inyectada acá — el resto del módulo no cambia."""

    async def send(self, *, to_email: str, subject: str, body: str) -> str:
        logger.info("EMAIL (dev, no enviado) to=%s subject=%r body=%r", to_email, subject, body)
        return "logged_only"


_default_email_sender: EmailSender = LoggingEmailSender()


def _safe_format(template: str, context: dict[str, str]) -> str:
    """Reemplaza `{variable}` con `context`; una clave faltante se
    reemplaza por cadena vacía en vez de lanzar `KeyError` — plantillas
    con variables que el llamador olvidó pasar no deben romper el envío
    de la notificación (DED-29)."""

    class _SafeDict(dict):
        def __missing__(self, key: str) -> str:
            return ""

    formatter = string.Formatter()
    return formatter.vformat(template, (), _SafeDict(**context))


class NotificationTemplateService:
    @staticmethod
    async def create(
        db: AsyncSession, *, company_id: int, payload: schemas.NotificationTemplateCreate
    ) -> models.NotificationTemplate:
        template = models.NotificationTemplate(
            company_id=company_id, code=payload.code,
            subject_template=payload.subject_template, body_template=payload.body_template,
        )
        db.add(template)
        try:
            await db.commit()
        except IntegrityError as exc:
            await db.rollback()
            if "uq_notification_templates_company_code" in str(exc.orig):
                raise ConflictError(f"Ya existe una plantilla con code='{payload.code}'") from exc
            raise
        await db.refresh(template)
        return template

    @staticmethod
    async def update(
        db: AsyncSession, *, company_id: int, code: str, payload: schemas.NotificationTemplateUpdate
    ) -> models.NotificationTemplate:
        template = await NotificationTemplateService.get_by_code(db, company_id=company_id, code=code)
        if payload.subject_template is not None:
            template.subject_template = payload.subject_template
        if payload.body_template is not None:
            template.body_template = payload.body_template
        await db.commit()
        await db.refresh(template)
        return template

    @staticmethod
    async def get_by_code(db: AsyncSession, *, company_id: int, code: str) -> models.NotificationTemplate:
        result = await db.execute(
            select(models.NotificationTemplate).where(
                models.NotificationTemplate.company_id == company_id, models.NotificationTemplate.code == code
            )
        )
        template = result.scalar_one_or_none()
        if template is None:
            raise NotFoundError(f"Plantilla '{code}' no encontrada")
        return template

    @staticmethod
    async def list(db: AsyncSession, *, company_id: int) -> list[models.NotificationTemplate]:
        result = await db.execute(
            select(models.NotificationTemplate)
            .where(models.NotificationTemplate.company_id == company_id)
            .order_by(models.NotificationTemplate.code)
        )
        return list(result.scalars().all())


class NotificationService:
    @staticmethod
    async def send(
        db: AsyncSession, *, company_id: int, payload: schemas.NotificationSend,
        recipient_email: str | None = None, email_sender: EmailSender | None = None,
    ) -> models.Notification:
        """Punto de entrada único, pensado para ser llamado tanto desde el
        router (`POST /notifications/send`) como desde el código de otros
        módulos (ej. `sales` notificando "orden confirmada" a un vendedor
        interno — integración cruzada, TODO de cada módulo consumidor, no
        de este)."""
        if payload.template_code:
            template = await NotificationTemplateService.get_by_code(
                db, company_id=company_id, code=payload.template_code
            )
            title = _safe_format(template.subject_template, payload.context)
            body = _safe_format(template.body_template, payload.context)
        elif payload.title is not None and payload.body is not None:
            # Equivalente a `payload.has_direct_content()` pero escrito así
            # para que mypy pueda angostar `str | None` a `str` (el método
            # no es un `TypeGuard`, así que asignar tras llamarlo dejaba
            # `title`/`body` tipados como `str | None` pese a la garantía
            # real en runtime — hallazgo de la auditoría de tipos, sep-2026).
            title = payload.title
            body = payload.body
        else:
            raise ValidationError("Debe enviarse 'template_code' o ambos 'title' y 'body'")

        email_status = None
        if payload.channel == schemas.NotificationChannelEnum.email:
            if not recipient_email:
                raise ValidationError("channel='email' requiere el correo del destinatario (recipient_email)")
            sender = email_sender or _default_email_sender
            email_status = await sender.send(to_email=recipient_email, subject=title, body=body)

        notification = models.Notification(
            company_id=company_id,
            recipient_user_id=payload.recipient_user_id,
            channel=payload.channel.value,
            title=title,
            body=body,
            template_code=payload.template_code,
            email_status=email_status,
        )
        db.add(notification)
        await db.commit()
        await db.refresh(notification)
        return notification

    @staticmethod
    async def list_for_user(
        db: AsyncSession, *, company_id: int, user_id: int, unread_only: bool = False
    ) -> list[models.Notification]:
        stmt = select(models.Notification).where(
            models.Notification.company_id == company_id, models.Notification.recipient_user_id == user_id
        )
        if unread_only:
            stmt = stmt.where(models.Notification.read_at.is_(None))
        result = await db.execute(stmt.order_by(models.Notification.created_at.desc()))
        return list(result.scalars().all())

    @staticmethod
    async def mark_read(db: AsyncSession, *, company_id: int, user_id: int, notification_id: int) -> models.Notification:
        result = await db.execute(
            select(models.Notification).where(
                models.Notification.company_id == company_id, models.Notification.id == notification_id
            )
        )
        notification = result.scalar_one_or_none()
        if notification is None:
            raise NotFoundError(f"Notificación {notification_id} no encontrada")
        if notification.recipient_user_id != user_id:
            # Mismo tratamiento que un recurso ajeno: 404, no 403 — no
            # confirmamos ni la existencia ni el dueño real a quien no es
            # el destinatario (evita enumeración).
            raise NotFoundError(f"Notificación {notification_id} no encontrada")
        if notification.read_at is None:
            from sqlalchemy import func

            notification.read_at = func.now()
            await db.commit()
            await db.refresh(notification)
        return notification

    @staticmethod
    async def mark_all_read(db: AsyncSession, *, company_id: int, user_id: int) -> int:
        from sqlalchemy import CursorResult, func

        result = await db.execute(
            update(models.Notification)
            .where(
                models.Notification.company_id == company_id,
                models.Notification.recipient_user_id == user_id,
                models.Notification.read_at.is_(None),
            )
            .values(read_at=func.now())
        )
        await db.commit()
        # `AsyncSession.execute()` está tipado como `Result[Any]` en los
        # stubs de SQLAlchemy 2.0 sin distinguir el caso de un `update()`
        # de Core, que en runtime siempre devuelve un `CursorResult` real
        # con `.rowcount` (confirmado — asyncpg lo soporta). El cast es
        # solo para el checker de tipos, no cambia el comportamiento.
        assert isinstance(result, CursorResult)
        return result.rowcount or 0
