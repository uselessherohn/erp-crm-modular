"""
Módulo 2 — contacts (spec sección 2.3).

Entidad única Contact con flags no excluyentes is_customer/is_vendor/
is_patient/is_lead. Reutilizada por purchasing, sales/ecommerce, medical,
website (módulos futuros, no construidos todavía).

pg_trgm/GIN obligatorio en `name` (spec 1.1, DoD explícito para contacts) —
el índice se crea en la migración (op.execute CREATE INDEX ... USING gin),
SQLAlchemy no tiene una forma declarativa nativa de expresar GIN+trgm ops.

ExternalMigrationMixin (spec sección 6) NO se aplica — sin proyecto de
migración contratado (STATE.md §7). Se agrega vía ALTER TABLE el día que
exista un cliente con migración real, no antes.
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Contact(Base):
    __tablename__ = "contacts"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    company_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("companies.id"), nullable=False, index=True)

    name: Mapped[str] = mapped_column(String(300), nullable=False)

    # No excluyentes entre sí (spec 2.3) — un contacto puede ser cliente y
    # paciente a la vez.
    is_customer: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    is_vendor: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    is_patient: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    is_lead: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")

    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    # RTN en Honduras (Registro Tributario Nacional) — nombre genérico
    # tax_id, mismo campo que Company.tax_id, para no acoplar el modelo a
    # un país específico pese al mercado objetivo actual.
    tax_id: Mapped[str | None] = mapped_column(String(50), nullable=True)
    address: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # credit_limit: hallazgo retroactivo del módulo 6 (accounting, Motor de
    # Contención Financiera, DED-12) — mismo patrón que reserved_quantity
    # agregado retroactivamente a inventory desde sales. NULL = sin límite
    # de crédito configurado (no bloquea por crédito excedido, solo por
    # deuda vencida si aplica).
    credit_limit: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)

    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    created_by: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("users.id"), nullable=True)
    updated_by: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("users.id"), nullable=True)

