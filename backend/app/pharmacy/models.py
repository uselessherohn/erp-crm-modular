"""
Módulo 16 — pharmacy: dispensación + verificación clínica (spec 8.3,
"Dispensación [core]" + "Verificación Clínica [core]" + "Sustancias
Controladas [core]" + "POS Farmacia [core]"). Primer módulo del paquete
Farmacéutico — `depende_de: [1, 2, 3, 6]` (Núcleo, contacts, inventory,
accounting mínimos — NO depende de `medical`, aunque se integra con él
si está activo).

DECISIONES DEDUCIBLE/AMBIGUO de este módulo:

- DED-45: FEFO (spec 8.1/8.3, "requiere inventory mínimo — lotes/FEFO/
  stock") no existe en `inventory` — su propio docstring lo declara
  explícitamente fuera de alcance de ese cierre ("FEFO/FIFO/LIFO... TODO
  explícito"). `pharmacy` es el primer módulo que realmente lo necesita,
  así que la selección FEFO (consumir el lote con vencimiento más
  próximo primero) se implementa ACÁ, consumiendo las primitivas ya
  reales de `inventory` (`Lot.expiry_date`, `StockLevel`,
  `StockService.ship`) — sin modificar el módulo 3 ya cerrado y probado.
  Una dispensación de una cantidad que excede un solo lote genera
  automáticamente varias `DispensationLine` (una por lote consumido).
- DED-46: "Sustancias Controladas" marca productos controlados con una
  tabla propia de `pharmacy` (`ControlledSubstanceProduct`, FK a
  `inventory.Product`), NO agregando una columna a `inventory.Product` —
  evita modificar el esquema de un módulo ajeno ya cerrado/probado por
  una necesidad que es específica de Farmacéutico.
- DED-47: "Verificación Clínica" — si el paquete `medical` está activo
  para la compañía **y** el contacto tiene `is_patient=true`, se
  consultan las alergias reales del paciente (`ClinicalRecordEntry` tipo
  `allergy`, vía `ClinicalRecordService.list_for_patient`, mismo patrón
  de reuso cruzado que `medical` llamando a `accounting`/`notifications`).
  En cualquier otro caso — `medical` inactivo, O activo pero el contacto
  no es un paciente de `medical` (DED-48: un cliente de mostrador de
  farmacia no tiene por qué tener ese flag) — se exige un formulario
  mínimo de alergias capturado en el propio flujo de dispensación
  (`allergy_check_notes` obligatorio) — dato redundante declarado
  explícitamente como tal por la spec, no una limitación oculta.
- DED-48: paciente/cliente de farmacia = cualquier `Contact`, sin exigir
  `is_patient=true` — un cliente de mostrador no es necesariamente un
  paciente de `medical` (que puede ni siquiera estar activo).
- DED-49: "POS Farmacia" (venta rápida con o sin receta) reutiliza la
  MISMA entidad `DispensationOrder` en vez de un documento POS separado
  — una venta de mostrador sin receta es, estructuralmente, una
  dispensación con `prescription_id=NULL` y `walk_in_reference` opcional,
  más los campos de cobro (`payment_method`/`amount_charged`). Crear una
  segunda entidad casi idéntica solo para distinguir "con receta" de
  "sin receta" habría duplicado toda la lógica de FEFO/verificación/
  sustancias controladas sin necesidad real.
- DED-50: anular una dispensación (`void`) NO revierte el descuento de
  inventario — la spec no describe un flujo de devolución/reingreso de
  producto dispensado. TODO explícito si se necesita una devolución real
  (con sus propias reglas: ¿se puede devolver un controlado? ¿el lote
  original sigue vigente?).
- Interacciones [extendido], Aseguradoras [extendido], Reposición a
  Droguerías [extendido], MTM [extendido] y Multi-sucursal [core, si
  aplica] — NO construidos en este cierre (regla 1 del Mensaje 0, son
  módulos separados en la tabla, 17-21). Multi-sucursal en particular ya
  queda parcialmente resuelto por diseño: `DispensationOrder.warehouse_id`
  es obligatorio y el llamador (router/frontend) siempre pasa el almacén
  de la sucursal autenticada — no hay lógica adicional que agregar
  cuando ese módulo se declare explícitamente construido.
"""
from __future__ import annotations

import enum
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Numeric,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class DispensationStatusEnum(str, enum.Enum):
    dispensed = "dispensed"
    voided = "voided"


DISPENSATION_STATUSES = tuple(s.value for s in DispensationStatusEnum)


class AllergyCheckSourceEnum(str, enum.Enum):
    medical_record = "medical_record"
    form = "form"


ALLERGY_CHECK_SOURCES = tuple(s.value for s in AllergyCheckSourceEnum)


class ControlledSubstanceProduct(Base):
    """Sustancias Controladas [core] — marca de producto. Ver DED-46."""

    __tablename__ = "controlled_substance_products"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    company_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("companies.id"), nullable=False, index=True)
    product_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("products.id"), nullable=False, index=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    created_by: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("users.id"), nullable=True)

    __table_args__ = (
        UniqueConstraint("company_id", "product_id", name="uq_controlled_substance_products_company_product"),
    )


class DispensationOrder(Base):
    """Dispensación [core] + Verificación Clínica [core] + POS Farmacia
    [core] (DED-49). Cabecera."""

    __tablename__ = "dispensation_orders"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    company_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("companies.id"), nullable=False, index=True)

    warehouse_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("warehouses.id"), nullable=False, index=True)
    patient_contact_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("contacts.id"), nullable=False, index=True)
    dispensed_by: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"), nullable=False)

    document_number: Mapped[str] = mapped_column(String(50), nullable=False)

    # Receta externa de medical (si está activo y aplica) o referencia
    # libre a una receta en papel/externa (DED-49) — mutuamente
    # excluyentes en la práctica, ninguno de los dos es obligatorio (POS
    # sin receta: ambos NULL).
    prescription_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("prescriptions.id"), nullable=True)
    walk_in_reference: Mapped[str | None] = mapped_column(String(300), nullable=True)

    allergy_check_source: Mapped[str] = mapped_column(String(20), nullable=False)
    allergy_check_notes: Mapped[str | None] = mapped_column(String(1000), nullable=True)

    payment_method: Mapped[str | None] = mapped_column(String(50), nullable=True)
    amount_charged: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)

    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="dispensed")
    voided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    void_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)

    dispensed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        UniqueConstraint("company_id", "document_number", name="uq_dispensation_orders_company_document_number"),
        CheckConstraint(f"status IN {DISPENSATION_STATUSES}", name="ck_dispensation_orders_status"),
        CheckConstraint(f"allergy_check_source IN {ALLERGY_CHECK_SOURCES}", name="ck_dispensation_orders_allergy_source"),
    )


class DispensationLine(Base):
    """Una fila por (producto, lote) efectivamente consumido — FEFO puede
    generar varias líneas para un mismo producto si un lote no alcanza
    (DED-45)."""

    __tablename__ = "dispensation_lines"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    company_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("companies.id"), nullable=False, index=True)
    dispensation_order_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("dispensation_orders.id"), nullable=False, index=True)

    product_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("products.id"), nullable=False, index=True)
    lot_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("lots.id"), nullable=True)
    quantity: Mapped[Decimal] = mapped_column(Numeric(14, 4), nullable=False)

    __table_args__ = (
        CheckConstraint("quantity > 0", name="ck_dispensation_lines_quantity_positive"),
    )


class ControlledSubstanceLogEntry(Base):
    """Libro de registro obligatorio [core] — append-only (mismo criterio
    que `audit`/`StockMovement`: nunca se UPDATE/DELETE, solo se agregan
    filas). Se genera automáticamente cuando una `DispensationLine`
    corresponde a un producto marcado como controlado."""

    __tablename__ = "controlled_substance_log_entries"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    company_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("companies.id"), nullable=False, index=True)

    dispensation_line_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("dispensation_lines.id"), nullable=False, index=True)
    product_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("products.id"), nullable=False, index=True)
    patient_contact_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("contacts.id"), nullable=False, index=True)
    dispensed_by: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(14, 4), nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
