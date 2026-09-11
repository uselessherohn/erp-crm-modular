"""
Módulo 9 — medical (spec 8.2, subset de la tabla de módulos —
`modulos_erp_crm_v10_4.json` id 9): Expediente Clínico, Agenda Médica,
Consulta. `medical` — recetas (10), laboratorio (11), teleconsulta (12),
facturación médica básica (13), portal/mensajería (14), reserva pública de
citas (15) son módulos separados en la tabla — NO se construyen acá (regla
1 del Mensaje 0: no adelantar módulos futuros).

Paciente = `Contact` con `is_patient=true` (spec 8.2) — sin entidad
`Patient` propia, mismo criterio que "Lead" en `pipeline` (DED-15).

DECISIONES DEDUCIBLE/AMBIGUO de este módulo (registro formal en STATE.md
sección 4; resumen acá):

- DED-23: "Profesional" se modela como `User` directamente, sin una
  entidad `Practitioner`/`Professional` separada — la spec no exige un
  registro de profesionales distinto de la cuenta de acceso, y ningún otro
  módulo construido hasta ahora necesitó esa distinción. TODO explícito si
  en el futuro se requiere agendar profesionales sin cuenta de login
  (ej. personal que solo aparece en agenda pero nunca inicia sesión).
- DED-24: cifrado en reposo (spec 8.2, "Cifrado en reposo [core]") aplicado
  a `Consultation.diagnosis_text`, `Consultation.physical_exam`,
  `Consultation.treatment_plan` (texto libre clínico) y a
  `ClinicalRecordEntry.content` — NO a `Consultation.diagnosis_cie10`
  (código estandarizado, no texto libre, se deja en claro para
  interoperabilidad/reportería, mismo criterio que un código de producto)
  ni a `Appointment.reason`/`cancellation_reason` (motivo de la cita, no
  es diagnóstico ni nota clínica en sí — spec 8.2 limita el cifrado
  explícitamente a "diagnóstico y notas de consulta").
- DED-25: versionado "nunca se sobrescribe" (spec 8.2) implementado con
  auto-referencia (`previous_entry_id` en `ClinicalRecordEntry`,
  `previous_consultation_id`/`superseded_by_id` en `Consultation`) — una
  corrección crea una fila nueva enlazada a la anterior, nunca un UPDATE
  sobre el contenido clínico ya escrito. Sin endpoint de UPDATE/DELETE en
  ninguna de las dos entidades (Fase 2). El invariante "una sola consulta
  vigente por cita" se garantiza con `SELECT ... FOR UPDATE` (bloqueo de
  fila real en `AppointmentService._get_locked`/`ConsultationService.
  correct`), NO con un índice único parcial — se probó esa vía en Fase 4 y
  se revirtió: un índice único parcial de Postgres no es diferible, y se
  dispara al insertar la corrección antes de poder desmarcar la fila
  anterior en la misma transacción (ver migración, sección revertida).
- DED-26: "bloqueo de horario" (spec 8.2, Agenda Médica) implementado como
  restricción real de base de datos — `EXCLUDE USING gist` sobre
  `(professional_user_id, rango de tiempo)` para citas `scheduled`/
  `confirmed` — no una validación de aplicación que puede perder una
  carrera bajo concurrencia (mismo criterio de rigor que `reserved_quantity`
  en `inventory`/`sales`). Requiere la extensión `btree_gist` (migración).
- AMB-02: período de retención regulatoria del log de auditoría clínico
  (spec 8.2, "declarado explícitamente como AMBIGUO... no asumido en
  silencio") — sigue sin confirmación de Roberto. Registrado acá y en
  STATE.md, no resuelto en este cierre.
- "own patients" (RBAC clínico, `medical:record:read-own-patients` /
  `medical:consultation:read-own-patients`) se define como: el actor tiene
  al menos una `Appointment` con ese `patient_contact_id` como
  `professional_user_id` propio. No se creó una tabla de asignación
  paciente↔profesional separada — la relación clínica nace de la Agenda.
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
    LargeBinary,
    Numeric,
    String,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class ClinicalRecordEntryTypeEnum(str, enum.Enum):
    antecedent = "antecedent"
    allergy = "allergy"
    diagnosis = "diagnosis"
    note = "note"


CLINICAL_RECORD_ENTRY_TYPES = tuple(t.value for t in ClinicalRecordEntryTypeEnum)


class AppointmentStatusEnum(str, enum.Enum):
    scheduled = "scheduled"
    confirmed = "confirmed"
    completed = "completed"
    cancelled = "cancelled"
    no_show = "no_show"


APPOINTMENT_STATUSES = tuple(s.value for s in AppointmentStatusEnum)
APPOINTMENT_ACTIVE_STATUSES = (AppointmentStatusEnum.scheduled.value, AppointmentStatusEnum.confirmed.value)


class ClinicalRecordEntry(Base):
    """Expediente Clínico [core] — entradas versionadas, nunca sobrescritas
    (DED-25). `content` cifrado con pgcrypto (DED-24)."""

    __tablename__ = "clinical_record_entries"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    company_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("companies.id"), nullable=False, index=True)

    patient_contact_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("contacts.id"), nullable=False, index=True)
    entry_type: Mapped[str] = mapped_column(String(20), nullable=False)

    # pgcrypto — ciphertext (bytea), nunca texto plano en la columna.
    content: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)

    previous_entry_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("clinical_record_entries.id"), nullable=True
    )
    author_user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"), nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        CheckConstraint(f"entry_type IN {CLINICAL_RECORD_ENTRY_TYPES}", name="ck_clinical_record_entries_type"),
        CheckConstraint("previous_entry_id IS NULL OR previous_entry_id <> id", name="ck_clinical_record_entries_not_own_previous"),
    )


class Appointment(Base):
    """Agenda Médica [core]. Bloqueo de horario real (DED-26) — ver
    `EXCLUDE USING gist` en la migración, no expresable como `CheckConstraint`
    declarativo de SQLAlchemy."""

    __tablename__ = "appointments"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    company_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("companies.id"), nullable=False, index=True)

    patient_contact_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("contacts.id"), nullable=False, index=True)
    professional_user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"), nullable=False, index=True)

    scheduled_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    scheduled_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="scheduled")

    reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    cancellation_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    created_by: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("users.id"), nullable=True)

    __table_args__ = (
        CheckConstraint(f"status IN {APPOINTMENT_STATUSES}", name="ck_appointments_status"),
        CheckConstraint("scheduled_end > scheduled_start", name="ck_appointments_end_after_start"),
    )


class Consultation(Base):
    """Consulta [core] — vinculada 1:1 (mientras esté vigente, ver
    `superseded_by_id`) a una cita de la Agenda. `diagnosis_text`,
    `physical_exam`, `treatment_plan` cifrados con pgcrypto (DED-24);
    `diagnosis_cie10` en claro (código estandarizado, DED-24)."""

    __tablename__ = "consultations"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    company_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("companies.id"), nullable=False, index=True)

    appointment_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("appointments.id"), nullable=False, index=True)
    patient_contact_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("contacts.id"), nullable=False, index=True)
    professional_user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"), nullable=False, index=True)

    physical_exam: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    diagnosis_cie10: Mapped[str | None] = mapped_column(String(10), nullable=True)
    diagnosis_text: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    treatment_plan: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)

    # DED-25: corrección = fila nueva enlazada, nunca UPDATE del contenido.
    previous_consultation_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("consultations.id"), nullable=True
    )
    superseded_by_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("consultations.id"), nullable=True)

    created_by: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        CheckConstraint("previous_consultation_id IS NULL OR previous_consultation_id <> id", name="ck_consultations_not_own_previous"),
        CheckConstraint("superseded_by_id IS NULL OR superseded_by_id <> id", name="ck_consultations_not_own_superseder"),
    )


# ---------------------------------------------------------------------------
# Módulo 10 — medical: recetas (spec 8.2, "Recetas [core]")
#
# DECISIONES DEDUCIBLE/AMBIGUO de este módulo:
#
# - DED-30: una `Prescription` (receta) se emite siempre dentro de una
#   `Consultation` (1 consulta -> 0..N recetas a lo largo del tiempo, ej.
#   una corrección posterior sigue siendo una consulta nueva por el
#   patrón de DED-25 en Consulta) — no existe receta "suelta" sin
#   consulta asociada, consistente con el flujo clínico real: no se
#   prescribe sin haber registrado antes el motivo/diagnóstico.
# - DED-31: cabecera (`Prescription`) + líneas (`PrescriptionLine`) — una
#   receta casi siempre incluye más de un medicamento; modelarla como una
#   sola fila con un medicamento habría forzado a crear "recetas" separadas
#   para una misma consulta cuando el médico prescribe 2+ medicamentos a
#   la vez, lo cual no refleja cómo se emite una receta en la práctica.
# - DED-32: sin cifrado pgcrypto en `PrescriptionLine` — spec 8.2 ("Cifrado
#   en reposo [core]") limita explícitamente el cifrado a "los campos de
#   diagnóstico y notas de consulta del Expediente Clínico"; los datos de
#   una receta (medicamento/dosis/vía/frecuencia/duración) no están en esa
#   lista. Se sigue la spec al pie de la letra en vez de extender el
#   alcance del cifrado por iniciativa propia — si Roberto considera que
#   debería cifrarse también, es una corrección de spec, no un DEDUCIBLE
#   de este cierre.
# - DED-33: sin patrón de corrección/versionado (a diferencia de Expediente
#   Clínico y Consulta) — la spec no exige "nunca se sobrescribe" para
#   Recetas explícitamente. Una receta emitida es inmutable (sin endpoint
#   UPDATE) pero se puede anular (`void`, con motivo) en vez de editarse —
#   más cercano al patrón de documentos `confirmed`/`cancelled` del resto
#   del ERP (ej. `SalesOrder`) que al patrón de corrección encadenada.
# - `dispensing_status` (spec 8.2): `not_applicable` si el paquete
#   `pharmacy` no está activo para la compañía, `pending` si está activo
#   (Farmacéutico/módulo 16+ aún no construido en este proyecto — cuando
#   se construya, ese módulo es quien transiciona `pending -> dispensed`,
#   no este). Se calcula al emitir la receta, no se persiste como un
#   default fijo, para que quede correcto incluso si el cliente activa
#   Farmacéutico después de tener recetas ya emitidas con `pharmacy`
#   inactivo en ese momento.
# ---------------------------------------------------------------------------
class PrescriptionDispensingStatusEnum(str, enum.Enum):
    not_applicable = "not_applicable"
    pending = "pending"
    dispensed = "dispensed"


DISPENSING_STATUSES = tuple(s.value for s in PrescriptionDispensingStatusEnum)


class Prescription(Base):
    """Recetas [core] — cabecera. Ver DED-30/31/33 arriba."""

    __tablename__ = "prescriptions"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    company_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("companies.id"), nullable=False, index=True)

    consultation_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("consultations.id"), nullable=False, index=True)
    patient_contact_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("contacts.id"), nullable=False, index=True)
    professional_user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"), nullable=False, index=True)

    notes: Mapped[str | None] = mapped_column(String(500), nullable=True)
    voided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    void_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)

    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    created_by: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"), nullable=False)


class PrescriptionLine(Base):
    """Recetas [core] — líneas de medicamento (DED-31)."""

    __tablename__ = "prescription_lines"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    company_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("companies.id"), nullable=False, index=True)
    prescription_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("prescriptions.id"), nullable=False, index=True)

    medication_name: Mapped[str] = mapped_column(String(300), nullable=False)
    dosage: Mapped[str] = mapped_column(String(100), nullable=False)
    route: Mapped[str] = mapped_column(String(100), nullable=False)
    frequency: Mapped[str] = mapped_column(String(100), nullable=False)
    duration: Mapped[str] = mapped_column(String(100), nullable=False)
    dispensing_status: Mapped[str] = mapped_column(String(20), nullable=False)

    __table_args__ = (
        CheckConstraint(f"dispensing_status IN {DISPENSING_STATUSES}", name="ck_prescription_lines_dispensing_status"),
    )


# ---------------------------------------------------------------------------
# Módulo 11 — medical: laboratorio (spec 8.2, "Laboratorio [extendido]")
#
# DECISIONES DEDUCIBLE/AMBIGUO de este módulo:
#
# - DED-34: cabecera (`LabOrder`) + líneas (`LabOrderTest`) — mismo
#   criterio que Recetas (DED-31): una orden de laboratorio casi siempre
#   solicita más de una prueba a la vez (ej. "hemograma completo" +
#   "glucosa" + "perfil lipídico" en la misma orden).
# - DED-35: "orden" y "resultado" viven en la MISMA fila (`LabOrderTest`),
#   no en dos tablas separadas — el resultado completa campos que ya
#   existen en la línea de la orden (transición `pending -> resulted`),
#   en vez de crear una entidad `LabResult` separada vinculada 1:1. Se
#   sigue el mismo criterio de "no crear una segunda tabla cuando una
#   transición de estado sobre la misma fila alcanza" ya usado en
#   `Appointment` (una cita no tiene una tabla `AppointmentCompletion`
#   separada).
# - DED-36: marcado de valor crítico (`is_critical`) es **explícito**
#   (un booleano que marca quien carga el resultado), no inferido
#   automáticamente comparando el valor contra el rango de referencia —
#   los rangos de referencia y los valores llegan en formatos
#   heterogéneos según la prueba ("70-100 mg/dL", "<5 UI/L", "Negativo",
#   "Positivo/Negativo") sin una unidad ni un formato numérico único que
#   parsear de forma confiable sin una tabla de catálogo de pruebas con
#   unidades normalizadas por prueba — fuera de alcance de este cierre.
#   TODO explícito si se necesita en el futuro un catálogo de pruebas
#   con rangos estructurados (`test_catalog`) que permita el cálculo
#   automático.
# - Adjuntos (spec 8.2, "carga de resultados vía attachments"): se
#   reutiliza `core.Attachment` (`entity_type='lab_order_test'`) — ver
#   `AttachmentService` en `app/core/services.py`, primer consumidor real
#   de esa tabla genérica.
# ---------------------------------------------------------------------------
class LabOrderStatusEnum(str, enum.Enum):
    ordered = "ordered"
    completed = "completed"
    cancelled = "cancelled"


LAB_ORDER_STATUSES = tuple(s.value for s in LabOrderStatusEnum)


class LabOrderTestStatusEnum(str, enum.Enum):
    pending = "pending"
    resulted = "resulted"


LAB_ORDER_TEST_STATUSES = tuple(s.value for s in LabOrderTestStatusEnum)


class LabOrder(Base):
    """Laboratorio [extendido] — cabecera. Ver DED-34/35 arriba."""

    __tablename__ = "lab_orders"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    company_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("companies.id"), nullable=False, index=True)

    consultation_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("consultations.id"), nullable=False, index=True)
    patient_contact_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("contacts.id"), nullable=False, index=True)
    professional_user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"), nullable=False, index=True)

    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="ordered")
    ordered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    created_by: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"), nullable=False)

    __table_args__ = (
        CheckConstraint(f"status IN {LAB_ORDER_STATUSES}", name="ck_lab_orders_status"),
    )


class LabOrderTest(Base):
    """Laboratorio [extendido] — líneas: una prueba solicitada, que luego
    se completa con su resultado en la misma fila (DED-35)."""

    __tablename__ = "lab_order_tests"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    company_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("companies.id"), nullable=False, index=True)
    lab_order_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("lab_orders.id"), nullable=False, index=True)

    test_name: Mapped[str] = mapped_column(String(300), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="pending")

    result_value: Mapped[str | None] = mapped_column(String(300), nullable=True)
    result_unit: Mapped[str | None] = mapped_column(String(50), nullable=True)
    reference_range_text: Mapped[str | None] = mapped_column(String(200), nullable=True)
    is_critical: Mapped[bool] = mapped_column(nullable=False, server_default="false")

    resulted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resulted_by: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("users.id"), nullable=True)

    __table_args__ = (
        CheckConstraint(f"status IN {LAB_ORDER_TEST_STATUSES}", name="ck_lab_order_tests_status"),
    )


# ---------------------------------------------------------------------------------
# Módulo 12 — medical: teleconsulta (spec 8.2, "Teleconsulta [extendido]")
#
# DECISIONES DEDUCIBLE/AMBIGUO de este módulo:
#
# - DED-37: la spec exige explícitamente integración con un proveedor
#   externo real (Twilio/Daily) y prohíbe implementar WebRTC propio salvo
#   pedido explícito — este sandbox no tiene salida de red hacia ningún
#   proveedor de videollamada (mismo tipo de limitación que
#   `EmailSender`/`AttachmentService`). Se implementa una interfaz real
#   (`TeleconsultationProvider`) con una implementación de desarrollo
#   (`DevStubTeleconsultationProvider`) que genera una URL de sala local
#   determinística sin llamar a ningún proveedor real — producción
#   reemplaza esta clase por un cliente real de Twilio/Daily inyectado,
#   el resto del módulo no cambia. NO se implementó WebRTC propio, tal
#   como la spec lo prohíbe salvo pedido explícito.
# - DED-38: `TeleconsultationSession` vinculada 1:1 (mientras esté vigente)
#   a una `Appointment` — igual criterio que `Consultation` en el módulo 9
#   (índice único parcial descartado por el mismo motivo ya documentado
#   en DED-25: no es diferible en Postgres; el invariante se garantiza
#   con el chequeo de "¿ya existe sesión activa para esta cita?" dentro
#   de la transacción de creación).
# - DED-39: sin grabación/almacenamiento de video — la spec no lo pide
#   ("sala de videollamada", no "grabación de videollamada") y grabar
#   consultas médicas tiene implicaciones regulatorias de consentimiento
#   que no están definidas en ningún AMB de este proyecto. Se guarda
#   únicamente metadata de la sesión (horarios, estado, URL de sala).
# ---------------------------------------------------------------------------------
class TeleconsultationStatusEnum(str, enum.Enum):
    scheduled = "scheduled"
    active = "active"
    ended = "ended"
    cancelled = "cancelled"


TELECONSULTATION_STATUSES = tuple(s.value for s in TeleconsultationStatusEnum)


class TeleconsultationSession(Base):
    """Teleconsulta [extendido] — sala de videollamada vinculada a una
    cita. Ver DED-37/38/39 arriba."""

    __tablename__ = "teleconsultation_sessions"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    company_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("companies.id"), nullable=False, index=True)

    appointment_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("appointments.id"), nullable=False, index=True)
    patient_contact_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("contacts.id"), nullable=False, index=True)
    professional_user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"), nullable=False, index=True)

    provider: Mapped[str] = mapped_column(String(50), nullable=False)
    room_external_id: Mapped[str] = mapped_column(String(200), nullable=False)
    join_url: Mapped[str] = mapped_column(String(500), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="scheduled")

    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    created_by: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"), nullable=False)

    __table_args__ = (
        CheckConstraint(f"status IN {TELECONSULTATION_STATUSES}", name="ck_teleconsultation_sessions_status"),
    )


# ---------------------------------------------------------------------------------------
# Módulo 13 — medical: facturación médica básica
# (spec 8.2, "Facturación Médica Básica [core]")
#
# DECISIONES DEDUCIBLE/AMBIGUO de este módulo:
#
# - DED-40: "si `accounting` está activo" (spec) se interpreta como "el
#   paquete `administrative` está activo para la compañía" — no existe
#   una activación granular por sub-módulo dentro de un paquete (spec
#   2.4: los paquetes son Administrativo/Médico/Farmacéutico/Web, sin
#   una bandera separada para "solo accounting dentro de administrative").
#   `accounting` es la pieza de `administrative` que expone el motor de
#   asientos, así que "activo" == paquete `administrative` activo.
# - DED-41: un solo monto por consulta (`amount`), sin líneas de
#   conceptos — la spec dice "recibo/factura por consulta", no un
#   desglose de conceptos facturables. TODO explícito si se necesita
#   facturar procedimientos/insumos por separado en el futuro.
# - DED-42: cuando `administrative` SÍ está activo, se reutiliza el
#   motor de asientos real (`accounting.InvoiceService`, sección 7.1)
#   creando un `Invoice` con `source_document_type='medical_consultation'`
#   — NO se duplica lógica de facturación dentro de `medical`. Esto
#   significa que el `Contact` del paciente debe tener `is_customer=true`
#   para poder facturarlo (`InvoiceService.create_draft` ya lo exige) —
#   `medical` no lo activa en silencio; si falta, se propaga el mismo
#   error que cualquier otro intento de facturar a un contacto sin ese
#   flag (regla general del ERP, no una regla nueva de este módulo).
# - Cuando `administrative` NO está activo, se genera un
#   `MedicalBillingRecord` en modo `simple_receipt` — comprobante simple
#   con numeración atómica real (`DocumentNumberingService`,
#   doc_type='medical_receipt') pero SIN asiento contable — declarado
#   como TODO explícito (spec) si el cliente activa Administrativo más
#   tarde: los recibos simples emitidos antes de esa activación no se
#   migran retroactivamente a asientos contables en este cierre.
# ---------------------------------------------------------------------------
class MedicalBillingModeEnum(str, enum.Enum):
    accounting_invoice = "accounting_invoice"
    simple_receipt = "simple_receipt"


MEDICAL_BILLING_MODES = tuple(m.value for m in MedicalBillingModeEnum)


class MedicalBillingStatusEnum(str, enum.Enum):
    issued = "issued"
    cancelled = "cancelled"


MEDICAL_BILLING_STATUSES = tuple(s.value for s in MedicalBillingStatusEnum)


class MedicalBillingRecord(Base):
    """Facturación Médica Básica [core]. Ver DED-40/41/42 arriba. Una fila
    por consulta facturada, sin importar el modo (`accounting_invoice`
    delega el detalle real a `accounting.Invoice` vía `invoice_id`;
    `simple_receipt` guarda el monto y el número directamente acá)."""

    __tablename__ = "medical_billing_records"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    company_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("companies.id"), nullable=False, index=True)

    consultation_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("consultations.id"), nullable=False, index=True)
    patient_contact_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("contacts.id"), nullable=False, index=True)
    professional_user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"), nullable=False, index=True)

    billing_mode: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="issued")

    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    currency_code: Mapped[str] = mapped_column(String(3), nullable=False, server_default="HNL")
    issue_date: Mapped[date] = mapped_column(Date, nullable=False)

    # billing_mode == accounting_invoice
    invoice_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("invoices.id"), nullable=True)
    # billing_mode == simple_receipt
    receipt_number: Mapped[str | None] = mapped_column(String(50), nullable=True)

    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancel_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    created_by: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"), nullable=False)

    __table_args__ = (
        CheckConstraint(f"billing_mode IN {MEDICAL_BILLING_MODES}", name="ck_medical_billing_records_mode"),
        CheckConstraint(f"status IN {MEDICAL_BILLING_STATUSES}", name="ck_medical_billing_records_status"),
        CheckConstraint("amount > 0", name="ck_medical_billing_records_amount_positive"),
    )
