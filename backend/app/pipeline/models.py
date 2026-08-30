"""
Módulo 7 — pipeline de leads/oportunidades sobre contacts (spec 2.3, 8.0).

Todo el contenido funcional de este módulo está clasificado
**[extendido, requiere paquete Administrativo]** en spec 8.0 — no es un
"core parcial" como purchasing/sales/accounting. Se construye igual porque
`modulos_erp_crm_v10_4.json` lo incluye explícitamente en la tabla de
módulos con dependencias reales (`depende_de: [2, 6]`), pero **es el
primer módulo del proyecto donde el gating por paquete (`require_package`,
ya scaffoldeado desde el módulo 1 pero nunca antes aplicado) se usa de
verdad** — spec dice literalmente que sin el paquete Administrativo activo
esto debe quedar `UNSUPPORTED_WITHOUT_ADMIN_PACKAGE` a nivel de feature
flag, no como error de sistema. Se reutiliza el código existente
`PACKAGE_NOT_LICENSED` (403) para esto — ver DED-19.

DECISIONES DEDUCIBLE/AMBIGUO de este módulo (registro formal en STATE.md
sección 4; resumen acá para que el modelo sea legible sin cruzar
documentos):

- DED-15: "Lead" (spec 2.3: Lead, Opportunity, Stage, Activity) NO es una
  tabla nueva — ya existe como `Contact.is_lead` (construido en el módulo
  2). Este módulo agrega `Opportunity`, `Stage` y `Activity` sobre
  `Contact` existente, sin duplicar su identidad.
- DED-16: `Stage` es configurable por compañía (spec sección 11: "cambio
  central de v9 — ya no un pipeline fijo"), con `is_won`/`is_lost`
  marcando etapas terminales. Un `CHECK` a nivel de fila impide que una
  misma etapa sea `is_won` y `is_lost` a la vez; la regla "debe existir al
  menos una etapa `is_won` y una `is_lost` para poder cerrar oportunidades"
  es una regla de conjunto (no de fila) — se valida en el servicio
  (Fase 2), no en un constraint de base.
- DED-17: **Lead scoring [extendido] explícitamente NO construido en este
  cierre** — `Opportunity` no tiene campo de score. Spec 8.0 lo menciona
  junto a kanban/actividades como parte del mismo bullet [extendido], pero
  scoring requiere una fórmula/config propia no especificada en ningún
  lado del corpus — se deja como TODO en vez de inventar una heurística.
- DED-18/AMBIGUO: la spec no especifica si el kanban permite mover una
  oportunidad libremente entre cualquier etapa o si hay una máquina de
  estados estricta. Interpretación adoptada: movimiento libre entre etapas
  NO terminales (kanban real, sin restricción de orden), pero alcanzar una
  etapa terminal (`is_won`/`is_lost`) es un comando explícito ("cerrar
  ganada"/"cerrar perdida"), no un simple `PATCH stage_id` — y una
  oportunidad cerrada no se puede mover de etapa sin "reabrir" primero
  (mismo rigor que el resto del proyecto, aunque el dominio sea más
  flexible que un documento financiero).
- DED-19: el bloqueo por paquete no licenciado reutiliza el error genérico
  ya existente `PACKAGE_NOT_LICENSED` (403, `PackageNotLicensedError`) en
  vez de inventar el literal `UNSUPPORTED_WITHOUT_ADMIN_PACKAGE` como
  código de error nuevo — mismo mecanismo, terminología de la spec es
  descriptiva, no un contrato de API distinto.
"""
from __future__ import annotations

import enum
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class OpportunityStatusEnum(str, enum.Enum):
    open = "open"
    won = "won"
    lost = "lost"


OPPORTUNITY_STATUSES = tuple(s.value for s in OpportunityStatusEnum)


class ActivityTypeEnum(str, enum.Enum):
    call = "call"
    email = "email"
    meeting = "meeting"
    note = "note"
    task = "task"


ACTIVITY_TYPES = tuple(t.value for t in ActivityTypeEnum)


class Stage(Base):
    """Etapa configurable del embudo — no hay pipeline fijo (spec sección
    11, cambio central de v9)."""

    __tablename__ = "stages"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    company_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("companies.id"), nullable=False, index=True)

    name: Mapped[str] = mapped_column(String(100), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    is_won: Mapped[bool] = mapped_column(nullable=False, server_default="false")
    is_lost: Mapped[bool] = mapped_column(nullable=False, server_default="false")
    is_active: Mapped[bool] = mapped_column(nullable=False, server_default="true")

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        CheckConstraint("NOT (is_won AND is_lost)", name="ck_stages_won_xor_lost"),
        UniqueConstraint("company_id", "name", name="uq_stages_company_name"),
    )


class Opportunity(Base):
    __tablename__ = "opportunities"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    company_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("companies.id"), nullable=False, index=True)

    contact_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("contacts.id"), nullable=False, index=True)
    stage_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("stages.id"), nullable=False, index=True)
    owner_user_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("users.id"), nullable=True)

    name: Mapped[str] = mapped_column(String(300), nullable=False)
    amount: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)
    currency_code: Mapped[str] = mapped_column(String(3), nullable=False, server_default="HNL")
    expected_close_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    status: Mapped[str] = mapped_column(String(10), nullable=False, server_default="open")
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    lost_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # version: bloqueo optimista — mover de etapa (kanban) es una mutación
    # concurrente esperada (dos usuarios arrastrando la misma tarjeta).
    version: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    created_by: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("users.id"), nullable=True)
    updated_by: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("users.id"), nullable=True)

    __table_args__ = (
        CheckConstraint(f"status IN {OPPORTUNITY_STATUSES}", name="ck_opportunities_status"),
        CheckConstraint("amount IS NULL OR amount >= 0", name="ck_opportunities_amount_nonneg"),
    )

    activities: Mapped[list["Activity"]] = relationship(back_populates="opportunity", lazy="selectin")


class Activity(Base):
    """Actividad registrada contra un contacto — con o sin oportunidad
    asociada (spec: nutrición de leads antes de calificar)."""

    __tablename__ = "activities"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    company_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("companies.id"), nullable=False, index=True)

    contact_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("contacts.id"), nullable=False, index=True)
    opportunity_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("opportunities.id"), nullable=True, index=True
    )

    activity_type: Mapped[str] = mapped_column(String(10), nullable=False)
    subject: Mapped[str] = mapped_column(String(300), nullable=False)
    notes: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    created_by: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("users.id"), nullable=True)

    __table_args__ = (
        CheckConstraint(f"activity_type IN {ACTIVITY_TYPES}", name="ck_activities_activity_type"),
    )

    opportunity: Mapped["Opportunity | None"] = relationship(back_populates="activities", lazy="selectin")
