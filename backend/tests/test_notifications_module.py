"""
Tests de integración del módulo notifications — contra PostgreSQL real.
Mismo patrón que sales/medical: capa de servicio directa.
"""
from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from sqlalchemy import text

from app import models_registry  # noqa: F401
from app.core import models as core_models
from app.core import schemas as core_schemas
from app.core.services import UserService
from app.database import AsyncSessionLocal
from app.notifications import schemas as notifications_schemas
from app.notifications.services import (
    EmailSender,
    NotificationService,
    NotificationTemplateService,
)
from app.shared.exceptions import ConflictError, NotFoundError, ValidationError


@pytest_asyncio.fixture
async def db():
    async with AsyncSessionLocal() as session:
        yield session
        await session.rollback()


@pytest_asyncio.fixture
async def company(db):
    unique = uuid.uuid4().hex[:8]
    c = core_models.Company(name=f"Test Co {unique}", tax_id=unique)
    db.add(c)
    await db.flush()
    await db.execute(text("SELECT set_config('app.current_company_id', :cid, false)"), {"cid": str(c.id)})
    await db.commit()
    return c


@pytest_asyncio.fixture
async def user(db, company):
    unique = uuid.uuid4().hex[:8]
    return await UserService.create_user(
        db, company_id=company.id,
        payload=core_schemas.UserCreate(email=f"user.{unique}@test.hn", full_name="Usuario Test", password="SuperSegura123"),
        created_by=None,
    )


class _FakeEmailSender(EmailSender):
    def __init__(self):
        self.calls: list[dict] = []

    async def send(self, *, to_email: str, subject: str, body: str) -> str:
        self.calls.append({"to_email": to_email, "subject": subject, "body": body})
        return "sent"


@pytest.mark.asyncio
async def test_send_in_app_direct_content(db, company, user):
    notification = await NotificationService.send(
        db, company_id=company.id,
        payload=notifications_schemas.NotificationSend(
            recipient_user_id=user.id, channel=notifications_schemas.NotificationChannelEnum.in_app,
            title="Bienvenido", body="Tu cuenta fue creada",
        ),
    )
    assert notification.title == "Bienvenido"
    assert notification.read_at is None
    assert notification.email_status is None


@pytest.mark.asyncio
async def test_send_requires_template_or_direct_content(db, company, user):
    with pytest.raises(ValidationError):
        await NotificationService.send(
            db, company_id=company.id,
            payload=notifications_schemas.NotificationSend(recipient_user_id=user.id),
        )


@pytest.mark.asyncio
async def test_template_rendering_with_missing_variable_does_not_raise(db, company, user):
    template = await NotificationTemplateService.create(
        db, company_id=company.id,
        payload=notifications_schemas.NotificationTemplateCreate(
            code="welcome", subject_template="Hola {name}", body_template="Bienvenido {name}, tu rol es {role}",
        ),
    )
    assert template.code == "welcome"

    notification = await NotificationService.send(
        db, company_id=company.id,
        payload=notifications_schemas.NotificationSend(
            recipient_user_id=user.id, template_code="welcome", context={"name": "Roberto"},
        ),
    )
    assert notification.title == "Hola Roberto"
    # "role" no se pasó en el contexto — placeholder faltante se reemplaza
    # por cadena vacía en vez de lanzar KeyError (DED-29).
    assert notification.body == "Bienvenido Roberto, tu rol es "


@pytest.mark.asyncio
async def test_template_code_must_be_unique_per_company(db, company):
    await NotificationTemplateService.create(
        db, company_id=company.id,
        payload=notifications_schemas.NotificationTemplateCreate(code="dup", subject_template="A", body_template="B"),
    )
    with pytest.raises(ConflictError):
        await NotificationTemplateService.create(
            db, company_id=company.id,
            payload=notifications_schemas.NotificationTemplateCreate(code="dup", subject_template="C", body_template="D"),
        )


@pytest.mark.asyncio
async def test_send_unknown_template_raises_not_found(db, company, user):
    with pytest.raises(NotFoundError):
        await NotificationService.send(
            db, company_id=company.id,
            payload=notifications_schemas.NotificationSend(recipient_user_id=user.id, template_code="no-existe"),
        )


@pytest.mark.asyncio
async def test_send_email_uses_injected_sender_and_records_status(db, company, user):
    fake_sender = _FakeEmailSender()
    notification = await NotificationService.send(
        db, company_id=company.id,
        payload=notifications_schemas.NotificationSend(
            recipient_user_id=user.id, channel=notifications_schemas.NotificationChannelEnum.email,
            title="Aviso", body="Contenido del correo",
        ),
        recipient_email="destino@test.hn",
        email_sender=fake_sender,
    )
    assert notification.email_status == "sent"
    assert len(fake_sender.calls) == 1
    assert fake_sender.calls[0]["to_email"] == "destino@test.hn"


@pytest.mark.asyncio
async def test_send_email_without_recipient_email_raises_validation_error(db, company, user):
    with pytest.raises(ValidationError):
        await NotificationService.send(
            db, company_id=company.id,
            payload=notifications_schemas.NotificationSend(
                recipient_user_id=user.id, channel=notifications_schemas.NotificationChannelEnum.email,
                title="Aviso", body="Contenido",
            ),
        )


@pytest.mark.asyncio
async def test_list_for_user_only_returns_own_notifications(db, company, user):
    unique = uuid.uuid4().hex[:8]
    other_user = await UserService.create_user(
        db, company_id=company.id,
        payload=core_schemas.UserCreate(email=f"other.{unique}@test.hn", full_name="Otro Usuario", password="SuperSegura123"),
        created_by=None,
    )
    await NotificationService.send(
        db, company_id=company.id,
        payload=notifications_schemas.NotificationSend(recipient_user_id=user.id, title="Para user", body="..."),
    )
    await NotificationService.send(
        db, company_id=company.id,
        payload=notifications_schemas.NotificationSend(recipient_user_id=other_user.id, title="Para other", body="..."),
    )

    mine = await NotificationService.list_for_user(db, company_id=company.id, user_id=user.id)
    assert len(mine) == 1
    assert mine[0].title == "Para user"


@pytest.mark.asyncio
async def test_mark_read_rejects_notification_of_another_user(db, company, user):
    unique = uuid.uuid4().hex[:8]
    other_user = await UserService.create_user(
        db, company_id=company.id,
        payload=core_schemas.UserCreate(email=f"other2.{unique}@test.hn", full_name="Otro Usuario 2", password="SuperSegura123"),
        created_by=None,
    )
    notification = await NotificationService.send(
        db, company_id=company.id,
        payload=notifications_schemas.NotificationSend(recipient_user_id=other_user.id, title="Ajena", body="..."),
    )
    with pytest.raises(NotFoundError):
        await NotificationService.mark_read(db, company_id=company.id, user_id=user.id, notification_id=notification.id)


@pytest.mark.asyncio
async def test_mark_read_and_mark_all_read(db, company, user):
    n1 = await NotificationService.send(
        db, company_id=company.id,
        payload=notifications_schemas.NotificationSend(recipient_user_id=user.id, title="Uno", body="..."),
    )
    await NotificationService.send(
        db, company_id=company.id,
        payload=notifications_schemas.NotificationSend(recipient_user_id=user.id, title="Dos", body="..."),
    )

    read_n1 = await NotificationService.mark_read(db, company_id=company.id, user_id=user.id, notification_id=n1.id)
    assert read_n1.read_at is not None

    unread_before = await NotificationService.list_for_user(db, company_id=company.id, user_id=user.id, unread_only=True)
    assert len(unread_before) == 1

    marked_count = await NotificationService.mark_all_read(db, company_id=company.id, user_id=user.id)
    assert marked_count == 1

    unread_after = await NotificationService.list_for_user(db, company_id=company.id, user_id=user.id, unread_only=True)
    assert len(unread_after) == 0


@pytest.mark.asyncio
async def test_rls_blocks_cross_tenant_notification_list():
    async with AsyncSessionLocal() as db_a, AsyncSessionLocal() as db_b:
        unique_a, unique_b = uuid.uuid4().hex[:8], uuid.uuid4().hex[:8]
        company_a = core_models.Company(name=f"Co A {unique_a}", tax_id=unique_a)
        company_b = core_models.Company(name=f"Co B {unique_b}", tax_id=unique_b)
        db_a.add(company_a)
        db_b.add(company_b)
        await db_a.flush()
        await db_b.flush()
        await db_a.execute(text("SELECT set_config('app.current_company_id', :cid, false)"), {"cid": str(company_a.id)})
        await db_b.execute(text("SELECT set_config('app.current_company_id', :cid, false)"), {"cid": str(company_b.id)})
        await db_a.commit()
        await db_b.commit()

        user_a = await UserService.create_user(
            db_a, company_id=company_a.id,
            payload=core_schemas.UserCreate(email=f"a.{unique_a}@test.hn", full_name="User A", password="SuperSegura123"),
            created_by=None,
        )
        await NotificationService.send(
            db_a, company_id=company_a.id,
            payload=notifications_schemas.NotificationSend(recipient_user_id=user_a.id, title="Solo de A", body="..."),
        )

        # Desde la sesión de la compañía B, listar "para user_a" bajo el
        # contexto de B (RLS activo) no devuelve nada — aislamiento real.
        from_b = await NotificationService.list_for_user(db_b, company_id=company_b.id, user_id=user_a.id)
        assert from_b == []

        await db_a.rollback()
        await db_b.rollback()


@pytest.mark.asyncio
async def test_mark_read_idempotent_and_no_way_to_unread(db, company, user):
    """Catálogo módulo 26: 'se marca como leída, no se puede des-leer'.
    Confirmado por dos ángulos: (1) mark_read() es idempotente —
    llamarlo dos veces no cambia read_at a un timestamp más nuevo; y
    (2) NotificationService no expone ningún método para volver
    read_at a NULL — no hay 'mark_unread' en el servicio ni ruta HTTP
    para eso, es estructuralmente imposible, no solo no usado."""
    notification = await NotificationService.send(
        db, company_id=company.id,
        payload=notifications_schemas.NotificationSend(recipient_user_id=user.id, title="X", body="..."),
    )
    first = await NotificationService.mark_read(db, company_id=company.id, user_id=user.id, notification_id=notification.id)
    first_read_at = first.read_at
    assert first_read_at is not None

    second = await NotificationService.mark_read(db, company_id=company.id, user_id=user.id, notification_id=notification.id)
    assert second.read_at == first_read_at  # no se pisa con un timestamp nuevo

    assert not hasattr(NotificationService, "mark_unread")
