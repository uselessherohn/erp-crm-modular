"""
Módulo 26 — notifications (spec 8.1, subset [core] — módulo Transversal,
`modulos_erp_crm_v10_4.json` id 26, `depende_de: [1]` únicamente):
Motor de Correos [core], Notificaciones In-App [core], Plantillas
Dinámicas [core]. [extendido] fuera de este cierre: Canales Adicionales
(SMS, push), Preferencias por Usuario.

Transversal: a diferencia de `pipeline`/`hr`/`medical`, este módulo NO
tiene `require_package` — está disponible para cualquier compañía sin
importar qué paquete (Administrativo/Médico/Farmacéutico/Web) tenga
contratado, igual que `reports` y `audit` completo (spec 2.2, matriz de
dependencias: los tres paquetes verticales listan `notifications` como
algo que *usan*, no algo que *habilitan* — la infraestructura en sí es
del Núcleo hacia arriba).

DECISIONES DEDUCIBLE/AMBIGUO de este módulo (registro formal en STATE.md
sección 4; resumen acá):

- DED-27: "Motor de Correos" [core] no implica un proveedor SMTP/API real
  configurado — el sandbox de este proyecto no tiene salida de red hacia
  ningún proveedor de correo (mismo tipo de limitación ya documentado con
  `ui.shadcn.com`/`cdn.playwright.dev`). Se implementa como una interfaz
  (`EmailSender`) con una implementación de desarrollo (`LoggingEmailSender`)
  que registra el envío como una fila (`channel='email'`, con
  `email_status`) en vez de entregarlo — mismo patrón que "no hay endpoint
  público para contratar paquetes, se activa directo contra la base"
  (documentado en `pipeline`/`medical`): la interfaz es real y el punto de
  integración queda listo, la entrega real es un TODO explícito de
  despliegue (variable de entorno con las credenciales del proveedor).
- DED-28: Notificación = siempre dirigida a un `User` (`recipient_user_id`),
  nunca a un `Contact` — las notificaciones a clientes/pacientes (ej.
  confirmación de pedido, recordatorio de cita) son responsabilidad del
  módulo que las dispara (ej. `sales`, `medical`) construyendo el mensaje
  y usando su propio canal (email al `Contact.email`), no de este motor
  genérico de notificaciones internas. Motor genérico ≠ mensajería a
  terceros — separación de responsabilidad explícita, no una limitación
  técnica.
- DED-29: "Plantillas Dinámicas" implementado con reemplazo de
  placeholders `{nombre_variable}` (equivalente a `str.format_map`, con
  claves faltantes reemplazadas por cadena vacía en vez de lanzar
  `KeyError` — ver `_safe_format` en `services.py`) — NO un motor de
  plantillas de propósito general (Jinja2) para evitar la superficie de
  ataque de ejecución de código/SSTI en contenido que puede incluir texto
  ingresado por el usuario en `context`.
- Sin RBAC granular de lectura: una notificación es inherentemente
  personal — `GET /notifications` siempre filtra por
  `recipient_user_id = actor.id`, sin excepción ni permiso "leer todas"
  (a diferencia de `hr`/`medical`, acá no hay noción de "ver las
  notificaciones de otro usuario").
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, CheckConstraint, DateTime, ForeignKey, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base

NOTIFICATION_CHANNELS = ("in_app", "email")
EMAIL_STATUSES = ("sent", "logged_only")


class NotificationTemplate(Base):
    """Plantillas Dinámicas [core]. `code` único por compañía — se
    referencia por código, no por id, para que el código que dispara la
    notificación no dependa de un id numérico de la base."""

    __tablename__ = "notification_templates"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    company_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("companies.id"), nullable=False, index=True)

    code: Mapped[str] = mapped_column(String(100), nullable=False)
    subject_template: Mapped[str] = mapped_column(String(300), nullable=False)
    body_template: Mapped[str] = mapped_column(Text, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (UniqueConstraint("company_id", "code", name="uq_notification_templates_company_code"),)


class Notification(Base):
    """Notificaciones In-App [core] + registro del Motor de Correos
    (DED-27) — una fila por notificación, sin importar el canal."""

    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    company_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("companies.id"), nullable=False, index=True)

    recipient_user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"), nullable=False, index=True)
    channel: Mapped[str] = mapped_column(String(10), nullable=False, server_default="in_app")

    title: Mapped[str] = mapped_column(String(300), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    template_code: Mapped[str | None] = mapped_column(String(100), nullable=True)

    email_status: Mapped[str | None] = mapped_column(String(20), nullable=True)

    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)

    __table_args__ = (
        CheckConstraint(f"channel IN {NOTIFICATION_CHANNELS}", name="ck_notifications_channel"),
        CheckConstraint(f"email_status IS NULL OR email_status IN {EMAIL_STATUSES}", name="ck_notifications_email_status"),
    )
