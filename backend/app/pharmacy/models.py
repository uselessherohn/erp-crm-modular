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
  Droguerías [extendido] y Multi-sucursal [core, si aplica] — NO
  construidos en este cierre (regla 1 del Mensaje 0, son módulos
  separados en la tabla, 17-21). Multi-sucursal en particular ya queda
  parcialmente resuelto por diseño: `DispensationOrder.warehouse_id`
  es obligatorio y el llamador (router/frontend) siempre pasa el almacén
  de la sucursal autenticada — no hay lógica adicional que agregar
  cuando ese módulo se declare explícitamente construido.

MTM / Consulta Farmacéutica (módulo 21, spec 8.3, "MTM / Consulta
Farmacéutica [extendido]") se agregó en un cierre posterior — ver
docstring de `MtmSession`/`MtmBillingRecord` más abajo para sus propias
decisiones DEDUCIBLE/AMBIGUO (DED-62 a DED-64).

DECISIONES DEDUCIBLE/AMBIGUO del módulo 17 (Interacciones [extendido]):

- DED-58: la spec (8.3) pide integración con una API externa de
  referencia (RxNorm/DrugBank) y dice explícitamente "no modelar una
  base propia desde cero salvo que se pida" — el sandbox de este
  proyecto no tiene salida de red hacia esos dominios (mismo caso que
  DED-37/DED-27). Mismo patrón: interfaz `DrugInteractionProvider`
  (abstracta) + `DevStubDrugInteractionProvider` (implementación de
  desarrollo) detrás de la misma interfaz. Roberto pidió explícitamente
  el seed pequeño para el stub (10-20 pares conocidos, severidad alta) —
  "salvo que se pida" aplica acá.
- DED-59: `inventory.Product` no tiene principio activo — se agrega
  `ProductActiveIngredient` (tabla propia de `pharmacy`, FK a
  `inventory.Product`), NO una columna en el módulo 3 ya cerrado. Mismo
  criterio que DED-46 (sustancias controladas). Un producto sin mapeo
  simplemente no participa en el chequeo — declarado explícitamente,
  nunca falla en silencio.
- DED-60: `DrugInteractionReferenceEntry` (el catálogo de pares
  conocidos) es una tabla GLOBAL, sin `company_id` — mismo criterio que
  `core.Permission` (spec sección 1): un par de principios activos no
  pertenece a una compañía, igual que no pertenecerá el día que se
  conecte la API real.
- DED-61: el chequeo es un endpoint de solo lectura independiente
  (`POST /pharmacy/interactions/check`), no una modificación al
  contrato ya congelado de `DispensationOrder` (módulo 16, cerrado y
  verificado) — el frontend lo llama antes de confirmar una
  dispensación y decide cómo mostrarlo; no bloquea nada a nivel de
  backend porque la spec no especifica un bloqueo duro, solo "chequeo".
"""
from __future__ import annotations

import enum
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class DispensationStatusEnum(enum.StrEnum):
    dispensed = "dispensed"
    voided = "voided"


DISPENSATION_STATUSES = tuple(s.value for s in DispensationStatusEnum)


class AllergyCheckSourceEnum(enum.StrEnum):
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


# ---------------------------------------------------------------------------
# Módulo 21 — pharmacy: MTM / Consulta Farmacéutica (spec 8.3, "MTM /
# Consulta Farmacéutica [extendido]"). `depende_de: [16]` en la tabla de
# módulos — reutiliza `Contact` (paciente/cliente) y el motor de
# asientos de `accounting`, no agrega dependencia nueva de paquete.
#
# DECISIONES DEDUCIBLE/AMBIGUO de este módulo:
#
# - DED-62: dos tablas, no una — `MtmSession` (contenido clínico de la
#   sesión: revisión de medicación, adherencia, efectos adversos) y
#   `MtmBillingRecord` (documento financiero, modo dual
#   `accounting_invoice`/`simple_receipt`) — mismo desacople que
#   `Consultation`/`MedicalBillingRecord` en el módulo 13 ("mismo patrón
#   que Facturación Médica Básica en 8.2", spec 8.3 explícito). La
#   diferencia real frente al módulo 13 es el disparador: acá NO es una
#   acción separada del usuario ("facturar esta consulta"), sino que
#   CERRAR la sesión genera el comprobante en la misma operación (spec
#   9, tabla de integraciones: "Sesión de asesoría cerrada" es
#   literalmente el disparador listado) — `MtmSessionService.close()`
#   hace ambas cosas en una sola transacción, no expone un endpoint de
#   facturación separado como sí existe para `medical`.
# - DED-63: gating igual que el módulo 13 — `accounting_invoice` si
#   `administrative` (paquete completo) está activo, `simple_receipt`
#   si no (spec sección 9, fila "Farmacéutico (MTM) → Administrativo
#   (accounting)": "Comprobante simple sin asiento contable si
#   Administrativo no está activo"). No se gatea con `accounting`
#   mínimo porque ese nivel mínimo (spec 8.3, cabecera del paquete) es
#   el que ya usa `pharmacy` para copagos/reclamos, sin exponer un
#   motor de asientos completo — mismo razonamiento que DED-40 en
#   `medical`.
# - DED-64: `patient_contact_id` es cualquier `Contact` de la compañía,
#   sin exigir `is_patient=true` — mismo criterio que DED-48
#   (dispensación): un cliente de MTM no tiene por qué ser paciente de
#   `medical`, que puede ni siquiera estar activo.
# ---------------------------------------------------------------------------
class MtmSessionStatusEnum(enum.StrEnum):
    open = "open"
    closed = "closed"
    cancelled = "cancelled"


MTM_SESSION_STATUSES = tuple(s.value for s in MtmSessionStatusEnum)


class MtmBillingModeEnum(enum.StrEnum):
    accounting_invoice = "accounting_invoice"
    simple_receipt = "simple_receipt"


MTM_BILLING_MODES = tuple(m.value for m in MtmBillingModeEnum)


class MtmSession(Base):
    """MTM / Consulta Farmacéutica [extendido] — spec 8.3. Ver DED-62/64
    arriba. `status='open'` mientras se captura la sesión;
    `'closed'` una vez facturada (ver `MtmSessionService.close`,
    genera el `MtmBillingRecord` en la misma transacción);
    `'cancelled'` si la sesión se agenda/inicia pero nunca se completa
    (nunca llega a generar comprobante — a diferencia de anular un
    comprobante ya emitido, que es `MtmBillingRecord.status`)."""

    __tablename__ = "pharmacy_mtm_sessions"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    company_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("companies.id"), nullable=False, index=True)

    patient_contact_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("contacts.id"), nullable=False, index=True)
    pharmacist_user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"), nullable=False, index=True)

    session_date: Mapped[Date] = mapped_column(Date, nullable=False)
    medication_review: Mapped[str] = mapped_column(Text, nullable=False)
    adherence_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    adverse_effects_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    recommendations: Mapped[str | None] = mapped_column(Text, nullable=True)

    fee_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    currency_code: Mapped[str] = mapped_column(String(3), nullable=False, server_default="HNL")

    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="open")
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancel_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    created_by: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"), nullable=False)

    __table_args__ = (
        CheckConstraint(f"status IN {MTM_SESSION_STATUSES}", name="ck_pharmacy_mtm_sessions_status"),
        CheckConstraint("fee_amount > 0", name="ck_pharmacy_mtm_sessions_fee_positive"),
    )


class MtmBillingRecord(Base):
    """Documento financiero de una sesión de MTM cerrada. Estructura
    deliberadamente idéntica a `medical.MedicalBillingRecord` (módulo
    13) — mismo modo dual, ver DED-62/63 arriba."""

    __tablename__ = "pharmacy_mtm_billing_records"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    company_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("companies.id"), nullable=False, index=True)

    session_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("pharmacy_mtm_sessions.id"), nullable=False, unique=True, index=True)

    billing_mode: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="issued")

    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    currency_code: Mapped[str] = mapped_column(String(3), nullable=False, server_default="HNL")
    issue_date: Mapped[Date] = mapped_column(Date, nullable=False)

    # billing_mode == accounting_invoice
    invoice_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("invoices.id"), nullable=True)
    # billing_mode == simple_receipt
    receipt_number: Mapped[str | None] = mapped_column(String(50), nullable=True)

    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancel_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        CheckConstraint(f"billing_mode IN {MTM_BILLING_MODES}", name="ck_pharmacy_mtm_billing_records_mode"),
        CheckConstraint("status IN ('issued', 'cancelled')", name="ck_pharmacy_mtm_billing_records_status"),
        CheckConstraint("amount > 0", name="ck_pharmacy_mtm_billing_records_amount_positive"),
    )


# ---------------------------------------------------------------------------
# Módulo 20 — pharmacy: Reposición a Droguerías (spec 8.3, "Reposición a
# Droguerías [extendido]": "sugerencia de reorden por punto de pedido,
# opcionalmente generando una PO en `purchasing` si el Administrativo
# completo está presente; si no, queda como lista exportable sin flujo
# de aprobación").
#
# DECISIONES DEDUCIBLE/AMBIGUO de este módulo:
#
# - DED-65: el punto de pedido se configura por producto+almacén
#   (`PharmacyReorderPoint`), no a nivel de producto solo — spec 8.3
#   nota multi-sucursal (v9): "cada sucursal es un almacén... nunca
#   contra el stock consolidado de la cadena" — un punto de pedido único
#   por producto ignoraría esa restricción explícita si una cadena tiene
#   sucursales con patrones de consumo distintos.
# - DED-66: "lista exportable" (sin `administrative`) se interpreta como
#   "el frontend puede exportar la tabla que ya devuelve el listado" —
#   NO se construyó un endpoint de exportación a CSV/PDF dedicado para
#   esto. `reports` (módulo 24) ya tiene ese mecanismo genérico para
#   quien lo necesite; duplicarlo acá sería alcance no pedido por la
#   spec (que solo exige que la lista exista, no un formato de archivo
#   específico).
# - DED-67: generar la PO no valida que `payload.lines` coincida
#   exactamente con las sugerencias vigentes — el pharmacista puede
#   ajustar cantidades/costos antes de confirmar (el costo unitario en
#   particular NO puede inferirse de la sugerencia: `purchasing` no
#   guarda un "costo esperado" por producto, solo el costo real de cada
#   PO ya creada). Mismo criterio de "el sistema sugiere, el humano
#   decide" que ya aplica en el resto del proyecto (ej. sugerencias de
#   reorden de cualquier ERP de referencia).
# ---------------------------------------------------------------------------
class PharmacyReorderPoint(Base):
    """Configuración de reorden por producto+almacén. Ver DED-65 arriba.
    No es la sugerencia en sí (esa se calcula al vuelo comparando esto
    contra `StockLevel`, no se persiste) — es solo el umbral configurado."""

    __tablename__ = "pharmacy_reorder_points"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    company_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("companies.id"), nullable=False, index=True)

    product_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("products.id"), nullable=False, index=True)
    warehouse_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("warehouses.id"), nullable=False, index=True)

    reorder_point: Mapped[Decimal] = mapped_column(Numeric(14, 4), nullable=False)
    reorder_quantity: Mapped[Decimal] = mapped_column(Numeric(14, 4), nullable=False)
    preferred_vendor_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("contacts.id"), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    created_by: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("users.id"), nullable=True)

    __table_args__ = (
        UniqueConstraint("company_id", "product_id", "warehouse_id", name="uq_pharmacy_reorder_points_product_warehouse"),
        CheckConstraint("reorder_point >= 0", name="ck_pharmacy_reorder_points_point_nonneg"),
        CheckConstraint("reorder_quantity > 0", name="ck_pharmacy_reorder_points_quantity_positive"),
    )


class ProductActiveIngredient(Base):
    """Interacciones [extendido] (spec 8.3). Ver DED-59 — `inventory.Product`
    no tiene principio activo; esta tabla, propia de `pharmacy`, lo mapea
    sin tocar el esquema del módulo 3. Un producto sin fila acá
    simplemente no participa en el chequeo de interacciones."""

    __tablename__ = "product_active_ingredients"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    company_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("companies.id"), nullable=False, index=True)
    product_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("products.id"), nullable=False, index=True)

    # Normalizado (minúsculas, sin espacios extra) para que el lookup
    # contra DrugInteractionReferenceEntry sea consistente sin importar
    # cómo se capturó el nombre comercial del producto.
    active_ingredient: Mapped[str] = mapped_column(String(200), nullable=False, index=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    created_by: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("users.id"), nullable=True)

    __table_args__ = (
        UniqueConstraint("company_id", "product_id", name="uq_product_active_ingredients_company_product"),
    )


class InteractionSeverityEnum(enum.StrEnum):
    moderate = "moderate"
    major = "major"


INTERACTION_SEVERITIES = tuple(s.value for s in InteractionSeverityEnum)


class DrugInteractionReferenceEntry(Base):
    """Catálogo de referencia — GLOBAL, sin `company_id` (DED-60). Seed
    pequeño a mano (10-20 pares conocidos, severidad alta) mientras no hay
    integración con una API externa real (DED-58). `ingredient_a` /
    `ingredient_b` se guardan siempre en orden alfabético (normalizados)
    para que el lookup sea independiente del orden de los dos productos
    que se estén dispensando juntos."""

    __tablename__ = "drug_interaction_reference_entries"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    ingredient_a: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    ingredient_b: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    severity: Mapped[str] = mapped_column(String(20), nullable=False)
    description: Mapped[str] = mapped_column(String(1000), nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        UniqueConstraint("ingredient_a", "ingredient_b", name="uq_drug_interaction_reference_pair"),
        CheckConstraint(f"severity IN {INTERACTION_SEVERITIES}", name="ck_drug_interaction_reference_severity"),
        CheckConstraint("ingredient_a < ingredient_b", name="ck_drug_interaction_reference_alpha_order"),
    )


# ---------------------------------------------------------------------------------------------
# Módulo 18 — Aseguradoras [extendido] (spec 8.3): copagos, reclamos,
# conciliación con accounting.
# ---------------------------------------------------------------------------------------------
CLAIM_STATUSES = ("pending", "submitted", "approved", "paid", "rejected")


class InsuranceClaimStatusEnum(enum.StrEnum):
    pending = "pending"
    submitted = "submitted"
    approved = "approved"
    paid = "paid"
    rejected = "rejected"


class InsuranceProvider(Base):
    """DED-62: la aseguradora ENVUELVE un `Contact` existente (mismo
    criterio que "cliente de farmacia = cualquier Contact", DED-55) en vez
    de ser una entidad aislada — así se reutiliza el motor real de
    `Invoice`/`Payment` de `accounting` para facturarle, sin reinventar un
    sub-libro contable propio."""

    __tablename__ = "insurance_providers"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    company_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("companies.id"), nullable=False, index=True)
    contact_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("contacts.id"), nullable=False, index=True)

    default_coverage_percentage: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        UniqueConstraint("company_id", "contact_id", name="uq_insurance_providers_company_contact"),
        CheckConstraint(
            "default_coverage_percentage IS NULL OR (default_coverage_percentage >= 0 AND default_coverage_percentage <= 100)",
            name="ck_insurance_providers_coverage_range",
        ),
    )


class PatientInsurancePolicy(Base):
    """Vínculo paciente↔aseguradora con su % de cobertura (DED-63:
    modelado como porcentaje, no copago fijo por medicamento — la spec no
    especifica reglas por producto, y un porcentaje simple es lo mínimo
    que sostiene "copagos, reclamos, conciliar cobrado vs. reclamado")."""

    __tablename__ = "patient_insurance_policies"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    company_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("companies.id"), nullable=False, index=True)
    patient_contact_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("contacts.id"), nullable=False, index=True)
    insurance_provider_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("insurance_providers.id"), nullable=False, index=True)

    policy_number: Mapped[str] = mapped_column(String(100), nullable=False)
    coverage_percentage: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        UniqueConstraint(
            "company_id", "patient_contact_id", "insurance_provider_id",
            name="uq_patient_insurance_policies_company_patient_provider",
        ),
        CheckConstraint("coverage_percentage >= 0 AND coverage_percentage <= 100", name="ck_patient_insurance_policies_coverage_range"),
    )


class InsuranceClaim(Base):
    """Reclamo — FK a `DispensationOrder` (módulo 16, YA CERRADO) sin
    modificar esa tabla, mismo criterio que DED-59/60/61 del módulo 17.

    Ciclo: pending -> submitted -> approved -> paid | rejected. Solo se
    contabiliza (Invoice real) al pasar a 'approved', y se liquida (Payment
    real) al pasar a 'paid' — 'submitted'/'rejected' nunca tocan
    `accounting`, así nunca hace falta reversar un asiento si rechazan un
    reclamo que nunca se llegó a booking (DED-64)."""

    __tablename__ = "insurance_claims"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    company_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("companies.id"), nullable=False, index=True)
    dispensation_order_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("dispensation_orders.id"), nullable=False, index=True)
    insurance_provider_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("insurance_providers.id"), nullable=False, index=True)
    patient_contact_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("contacts.id"), nullable=False, index=True)

    claim_number: Mapped[str] = mapped_column(String(50), nullable=False)

    amount_total: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    amount_patient_copay: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    amount_claimed_insurer: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)

    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="pending")
    # DED-40/42 (medical): 'administrative' activo -> se usa el motor real
    # de accounting (Invoice/Payment); si no, el reclamo solo lleva estado
    # y montos, sin generar ningún documento contable (TODO explícito).
    billing_mode: Mapped[str | None] = mapped_column(String(20), nullable=True)
    invoice_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("invoices.id"), nullable=True)
    payment_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("payments.id"), nullable=True)

    rejection_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    rejected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        UniqueConstraint("company_id", "dispensation_order_id", name="uq_insurance_claims_company_dispensation"),
        UniqueConstraint("company_id", "claim_number", name="uq_insurance_claims_company_claim_number"),
        CheckConstraint(f"status IN {CLAIM_STATUSES}", name="ck_insurance_claims_status"),
        CheckConstraint("amount_total = amount_patient_copay + amount_claimed_insurer", name="ck_insurance_claims_amounts_sum"),
        CheckConstraint("amount_patient_copay >= 0 AND amount_claimed_insurer >= 0", name="ck_insurance_claims_amounts_nonneg"),
    )
