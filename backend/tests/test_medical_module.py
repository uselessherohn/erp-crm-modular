"""
Tests de integración del módulo medical — contra PostgreSQL real.

Mismo patrón que test_sales_module.py / test_inventory_module.py: se llama
a la capa de servicio directamente (no vía HTTP), porque lo que estos
tests verifican es lógica de negocio + invariantes reales de base de datos
(cifrado pgcrypto, RLS, restricciones de exclusión concurrentes) — el
RBAC/gating de rutas se cubre en la suite de integración de frontend
(Fase 3), igual que en el resto de módulos administrativos.
"""
from __future__ import annotations

import asyncio
import uuid

import pytest
import pytest_asyncio
from sqlalchemy import text

from app import models_registry  # noqa: F401  (registra todos los modelos — user.active_warehouse_id -> warehouses)
from app.contacts import schemas as contacts_schemas
from app.contacts.services import ContactService
from app.core import models as core_models
from app.core import schemas as core_schemas
from app.core.services import UserService
from app.database import AsyncSessionLocal
from app.medical import schemas as medical_schemas
from app.medical.dependencies import ensure_public_booking_active
from app.medical.services import (
    AppointmentService,
    ClinicalRecordService,
    ConsultationService,
    LabOrderService,
    MedicalBillingService,
    PatientMessageService,
    PrescriptionService,
    PublicBookingService,
    TeleconsultationService,
    professional_has_treated,
)
from app.shared.exceptions import ConflictError, NotFoundError, PackageNotLicensedError, PackageSuspendedError, ValidationError


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
async def patient(db, company):
    return await ContactService.create_contact(
        db, company_id=company.id,
        payload=contacts_schemas.ContactCreate(name="Paciente Test", is_patient=True),
        created_by=None,
    )


@pytest_asyncio.fixture
async def professional(db, company):
    unique = uuid.uuid4().hex[:8]
    return await UserService.create_user(
        db, company_id=company.id,
        payload=core_schemas.UserCreate(
            email=f"dr.{unique}@test.hn", full_name="Dra. Test", password="SuperSegura123"
        ),
        created_by=None,
    )


def _appt_payload(patient_id, professional_id, start, end, reason="Consulta general"):
    return medical_schemas.AppointmentCreate(
        patient_contact_id=patient_id, professional_user_id=professional_id,
        scheduled_start=start, scheduled_end=end, reason=reason,
    )


from datetime import date, datetime, timedelta, timezone  # noqa: E402
from decimal import Decimal  # noqa: E402

_BASE = datetime(2026, 10, 1, 9, 0, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# Expediente Clínico — cifrado + versionado
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_clinical_record_entry_encrypted_at_rest(db, company, patient, professional):
    entry = await ClinicalRecordService.create_entry(
        db, company_id=company.id,
        payload=medical_schemas.ClinicalRecordEntryCreate(
            patient_contact_id=patient.id, entry_type=medical_schemas.ClinicalRecordEntryTypeEnum.note,
            content="Paciente refiere dolor de cabeza recurrente",
        ),
        author_user_id=professional.id,
    )
    assert entry.content == "Paciente refiere dolor de cabeza recurrente"

    # La fila cruda en la base NO debe tener el texto plano en ninguna forma.
    raw = (
        await db.execute(text("SELECT content FROM clinical_record_entries WHERE id = :id"), {"id": entry.id})
    ).scalar_one()
    assert b"dolor de cabeza" not in bytes(raw)

    # Pero pgp_sym_decrypt con la clave correcta sí lo recupera.
    from app.config import settings

    decrypted = (
        await db.execute(
            text("SELECT pgp_sym_decrypt(content, :key) FROM clinical_record_entries WHERE id = :id"),
            {"id": entry.id, "key": settings.pgcrypto_key},
        )
    ).scalar_one()
    assert decrypted == "Paciente refiere dolor de cabeza recurrente"


@pytest.mark.asyncio
async def test_clinical_record_entry_requires_patient_flag(db, company, professional):
    non_patient = await ContactService.create_contact(
        db, company_id=company.id, payload=contacts_schemas.ContactCreate(name="No Paciente", is_customer=True), created_by=None
    )
    with pytest.raises(ValidationError):
        await ClinicalRecordService.create_entry(
            db, company_id=company.id,
            payload=medical_schemas.ClinicalRecordEntryCreate(
                patient_contact_id=non_patient.id, entry_type=medical_schemas.ClinicalRecordEntryTypeEnum.note,
                content="No debería poder crearse",
            ),
            author_user_id=professional.id,
        )


@pytest.mark.asyncio
async def test_clinical_record_entry_correction_never_overwrites(db, company, patient, professional):
    original = await ClinicalRecordService.create_entry(
        db, company_id=company.id,
        payload=medical_schemas.ClinicalRecordEntryCreate(
            patient_contact_id=patient.id, entry_type=medical_schemas.ClinicalRecordEntryTypeEnum.allergy,
            content="Alergia a penicilina",
        ),
        author_user_id=professional.id,
    )
    correction = await ClinicalRecordService.create_entry(
        db, company_id=company.id,
        payload=medical_schemas.ClinicalRecordEntryCreate(
            patient_contact_id=patient.id, entry_type=medical_schemas.ClinicalRecordEntryTypeEnum.allergy,
            content="Alergia a penicilina y sulfas (corrección: se agregó sulfas)",
            previous_entry_id=original.id,
        ),
        author_user_id=professional.id,
    )

    entries = await ClinicalRecordService.list_for_patient(
        db, company_id=company.id, patient_contact_id=patient.id, actor_user_id=professional.id
    )
    by_id = {e.id: e for e in entries}
    # La original sigue existiendo, sin modificar.
    assert by_id[original.id].content == "Alergia a penicilina"
    assert by_id[correction.id].previous_entry_id == original.id


@pytest.mark.asyncio
async def test_clinical_record_read_logs_audit_with_correlation_id(db, company, patient, professional):
    entry = await ClinicalRecordService.create_entry(
        db, company_id=company.id,
        payload=medical_schemas.ClinicalRecordEntryCreate(
            patient_contact_id=patient.id, entry_type=medical_schemas.ClinicalRecordEntryTypeEnum.note, content="Nota",
        ),
        author_user_id=professional.id,
    )
    await ClinicalRecordService.get(db, company_id=company.id, entry_id=entry.id, actor_user_id=professional.id)

    logs = (
        await db.execute(
            text(
                "SELECT event, correlation_id FROM audit "
                "WHERE company_id = :cid AND entity_type = 'clinical_record_entry' AND entity_id = :eid "
                "AND event = 'medical.record.read'"
            ),
            {"cid": company.id, "eid": entry.id},
        )
    ).all()
    assert len(logs) >= 1
    assert all(row.correlation_id for row in logs)


# ---------------------------------------------------------------------------
# Agenda Médica — bloqueo de horario real
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_appointment_overlap_blocked(db, company, patient, professional):
    await AppointmentService.create(
        db, company_id=company.id,
        payload=_appt_payload(patient.id, professional.id, _BASE, _BASE + timedelta(minutes=30)),
        created_by=None,
    )
    with pytest.raises(ConflictError):
        await AppointmentService.create(
            db, company_id=company.id,
            payload=_appt_payload(patient.id, professional.id, _BASE + timedelta(minutes=15), _BASE + timedelta(minutes=45)),
            created_by=None,
        )


@pytest.mark.asyncio
async def test_appointment_back_to_back_not_blocked(db, company, patient, professional):
    """[start, end) — una cita que empieza exactamente cuando termina la
    anterior NO se considera traslape (spec: agenda continua sin huecos
    forzados)."""
    await AppointmentService.create(
        db, company_id=company.id,
        payload=_appt_payload(patient.id, professional.id, _BASE, _BASE + timedelta(minutes=30)),
        created_by=None,
    )
    second = await AppointmentService.create(
        db, company_id=company.id,
        payload=_appt_payload(patient.id, professional.id, _BASE + timedelta(minutes=30), _BASE + timedelta(minutes=60)),
        created_by=None,
    )
    assert second.id is not None


@pytest.mark.asyncio
async def test_appointment_overlap_blocked_under_concurrency(db, company, patient, professional):
    """Carrera real — N inserts concurrentes para el mismo profesional y
    horario traslapado; la restricción EXCLUDE (no un chequeo de
    aplicación) debe garantizar que gana como máximo 1."""

    async def _attempt(offset_minutes: int):
        async with AsyncSessionLocal() as session:
            await session.execute(text("SELECT set_config('app.current_company_id', :cid, false)"), {"cid": str(company.id)})
            try:
                await AppointmentService.create(
                    session, company_id=company.id,
                    payload=_appt_payload(
                        patient.id, professional.id,
                        _BASE + timedelta(minutes=offset_minutes), _BASE + timedelta(minutes=offset_minutes + 30),
                    ),
                    created_by=None,
                )
                return True
            except ConflictError:
                return False
            finally:
                await session.close()

    results = await asyncio.gather(*[_attempt(5) for _ in range(8)])
    assert sum(results) == 1


@pytest.mark.asyncio
async def test_appointment_confirm_reschedule_cancel(db, company, patient, professional):
    appointment = await AppointmentService.create(
        db, company_id=company.id,
        payload=_appt_payload(patient.id, professional.id, _BASE, _BASE + timedelta(minutes=30)),
        created_by=None,
    )
    confirmed = await AppointmentService.confirm(db, company_id=company.id, appointment_id=appointment.id)
    assert confirmed.status == "confirmed"

    rescheduled = await AppointmentService.reschedule(
        db, company_id=company.id, appointment_id=appointment.id,
        payload=medical_schemas.AppointmentReschedule(
            scheduled_start=_BASE + timedelta(days=1), scheduled_end=_BASE + timedelta(days=1, minutes=30),
            reason="Paciente solicitó cambio de horario",
        ),
    )
    assert rescheduled.status == "scheduled"
    assert "Reprogramada" in (rescheduled.reason or "")

    cancelled = await AppointmentService.cancel(
        db, company_id=company.id, appointment_id=appointment.id,
        payload=medical_schemas.AppointmentCancel(cancellation_reason="Paciente canceló"),
    )
    assert cancelled.status == "cancelled"

    with pytest.raises(ConflictError):
        await AppointmentService.cancel(
            db, company_id=company.id, appointment_id=appointment.id,
            payload=medical_schemas.AppointmentCancel(cancellation_reason="Doble cancelación"),
        )


# ---------------------------------------------------------------------------
# Consulta — 1:1 con cita, corrección sin sobrescritura
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_consultation_create_completes_appointment(db, company, patient, professional):
    appointment = await AppointmentService.create(
        db, company_id=company.id,
        payload=_appt_payload(patient.id, professional.id, _BASE, _BASE + timedelta(minutes=30)),
        created_by=None,
    )
    consultation = await ConsultationService.create(
        db, company_id=company.id,
        payload=medical_schemas.ConsultationCreate(
            appointment_id=appointment.id, physical_exam="Normal", diagnosis_cie10="J00",
            diagnosis_text="Resfriado común", treatment_plan="Reposo e hidratación",
        ),
        created_by=professional.id,
    )
    assert consultation.diagnosis_text == "Resfriado común"
    assert consultation.diagnosis_cie10 == "J00"

    refreshed_appointment = await AppointmentService.get(db, company_id=company.id, appointment_id=appointment.id)
    assert refreshed_appointment.status == "completed"


@pytest.mark.asyncio
async def test_consultation_diagnosis_encrypted_at_rest(db, company, patient, professional):
    appointment = await AppointmentService.create(
        db, company_id=company.id,
        payload=_appt_payload(patient.id, professional.id, _BASE, _BASE + timedelta(minutes=30)),
        created_by=None,
    )
    consultation = await ConsultationService.create(
        db, company_id=company.id,
        payload=medical_schemas.ConsultationCreate(
            appointment_id=appointment.id, diagnosis_text="Diagnóstico confidencial de prueba",
        ),
        created_by=professional.id,
    )
    raw = (
        await db.execute(text("SELECT diagnosis_text FROM consultations WHERE id = :id"), {"id": consultation.id})
    ).scalar_one()
    assert b"confidencial" not in bytes(raw)


@pytest.mark.asyncio
async def test_consultation_only_one_per_appointment(db, company, patient, professional):
    appointment = await AppointmentService.create(
        db, company_id=company.id,
        payload=_appt_payload(patient.id, professional.id, _BASE, _BASE + timedelta(minutes=30)),
        created_by=None,
    )
    await ConsultationService.create(
        db, company_id=company.id,
        payload=medical_schemas.ConsultationCreate(appointment_id=appointment.id, diagnosis_text="Primera"),
        created_by=professional.id,
    )
    with pytest.raises(ConflictError):
        await ConsultationService.create(
            db, company_id=company.id,
            payload=medical_schemas.ConsultationCreate(appointment_id=appointment.id, diagnosis_text="Duplicada"),
            created_by=professional.id,
        )


@pytest.mark.asyncio
async def test_consultation_correction_never_overwrites(db, company, patient, professional):
    appointment = await AppointmentService.create(
        db, company_id=company.id,
        payload=_appt_payload(patient.id, professional.id, _BASE, _BASE + timedelta(minutes=30)),
        created_by=None,
    )
    original = await ConsultationService.create(
        db, company_id=company.id,
        payload=medical_schemas.ConsultationCreate(appointment_id=appointment.id, diagnosis_text="Diagnóstico inicial"),
        created_by=professional.id,
    )
    corrected = await ConsultationService.correct(
        db, company_id=company.id, consultation_id=original.id,
        payload=medical_schemas.ConsultationCorrect(diagnosis_text="Diagnóstico corregido tras revisión de laboratorio"),
        created_by=professional.id,
    )

    # La original nunca cambió su contenido — se lee directo, sin pasar por
    # el "current" del appointment.
    original_reread = await ConsultationService.get(
        db, company_id=company.id, consultation_id=original.id, actor_user_id=professional.id
    )
    assert original_reread.diagnosis_text == "Diagnóstico inicial"
    assert original_reread.superseded_by_id == corrected.id
    assert corrected.previous_consultation_id == original.id

    # Y ahora sí puede crearse una consulta "actual" nueva para otra cita,
    # pero esta (ya corregida) libera el slot para... no, sigue siendo la
    # misma cita — una tercera corrección debe encadenar sobre `corrected`,
    # no sobre `original` (que ya está superseded).
    with pytest.raises(ConflictError):
        await ConsultationService.correct(
            db, company_id=company.id, consultation_id=original.id,
            payload=medical_schemas.ConsultationCorrect(diagnosis_text="Intento sobre la ya corregida"),
            created_by=professional.id,
        )


@pytest.mark.asyncio
async def test_consultation_requires_active_appointment(db, company, patient, professional):
    appointment = await AppointmentService.create(
        db, company_id=company.id,
        payload=_appt_payload(patient.id, professional.id, _BASE, _BASE + timedelta(minutes=30)),
        created_by=None,
    )
    await AppointmentService.cancel(
        db, company_id=company.id, appointment_id=appointment.id,
        payload=medical_schemas.AppointmentCancel(cancellation_reason="No asistió"),
    )
    with pytest.raises(ConflictError):
        await ConsultationService.create(
            db, company_id=company.id,
            payload=medical_schemas.ConsultationCreate(appointment_id=appointment.id, diagnosis_text="No debería crearse"),
            created_by=professional.id,
        )


# ---------------------------------------------------------------------------
# RBAC clínico "own patients"
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_professional_has_treated_true_only_after_appointment(db, company, patient, professional):
    assert not await professional_has_treated(
        db, company_id=company.id, professional_user_id=professional.id, patient_contact_id=patient.id
    )
    await AppointmentService.create(
        db, company_id=company.id,
        payload=_appt_payload(patient.id, professional.id, _BASE, _BASE + timedelta(minutes=30)),
        created_by=None,
    )
    assert await professional_has_treated(
        db, company_id=company.id, professional_user_id=professional.id, patient_contact_id=patient.id
    )


# ---------------------------------------------------------------------------
# RLS — aislamiento entre compañías
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_rls_blocks_cross_tenant_clinical_record_read():
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

        patient_a = await ContactService.create_contact(
            db_a, company_id=company_a.id, payload=contacts_schemas.ContactCreate(name="Paciente A", is_patient=True),
            created_by=None,
        )
        professional_a = await UserService.create_user(
            db_a, company_id=company_a.id,
            payload=core_schemas.UserCreate(email=f"dr.a.{unique_a}@test.hn", full_name="Dr. A", password="SuperSegura123"),
            created_by=None,
        )
        entry = await ClinicalRecordService.create_entry(
            db_a, company_id=company_a.id,
            payload=medical_schemas.ClinicalRecordEntryCreate(
                patient_contact_id=patient_a.id, entry_type=medical_schemas.ClinicalRecordEntryTypeEnum.note,
                content="Dato clínico de la compañía A",
            ),
            author_user_id=professional_a.id,
        )

        # Desde la sesión de la compañía B (RLS activo), la fila de A es invisible.
        with pytest.raises(NotFoundError):
            await ClinicalRecordService.get(
                db_b, company_id=company_b.id, entry_id=entry.id, actor_user_id=professional_a.id
            )

        await db_a.rollback()
        await db_b.rollback()


# ---------------------------------------------------------------------------
# Módulo 10 — Recetas
# ---------------------------------------------------------------------------
async def _issue_consultation(db, company, patient, professional):
    appointment = await AppointmentService.create(
        db, company_id=company.id,
        payload=_appt_payload(patient.id, professional.id, _BASE, _BASE + timedelta(minutes=30)),
        created_by=None,
    )
    return await ConsultationService.create(
        db, company_id=company.id,
        payload=medical_schemas.ConsultationCreate(appointment_id=appointment.id, diagnosis_text="Faringitis"),
        created_by=professional.id,
    )


@pytest.mark.asyncio
async def test_prescription_create_with_multiple_lines(db, company, patient, professional):
    consultation = await _issue_consultation(db, company, patient, professional)
    prescription = await PrescriptionService.create(
        db, company_id=company.id,
        payload=medical_schemas.PrescriptionCreate(
            consultation_id=consultation.id,
            lines=[
                medical_schemas.PrescriptionLineCreate(
                    medication_name="Amoxicilina", dosage="500mg", route="oral", frequency="cada 8 horas", duration="7 días",
                ),
                medical_schemas.PrescriptionLineCreate(
                    medication_name="Ibuprofeno", dosage="400mg", route="oral", frequency="cada 12 horas", duration="5 días",
                ),
            ],
        ),
        created_by=professional.id,
    )
    assert len(prescription.lines) == 2
    assert prescription.patient_contact_id == patient.id


@pytest.mark.asyncio
async def test_prescription_dispensing_status_depends_on_pharmacy_package(db, company, patient, professional):
    consultation = await _issue_consultation(db, company, patient, professional)
    prescription = await PrescriptionService.create(
        db, company_id=company.id,
        payload=medical_schemas.PrescriptionCreate(
            consultation_id=consultation.id,
            lines=[medical_schemas.PrescriptionLineCreate(
                medication_name="Paracetamol", dosage="500mg", route="oral", frequency="cada 8 horas", duration="3 días",
            )],
        ),
        created_by=professional.id,
    )
    # Sin paquete 'pharmacy' activo para esta compañía de prueba —
    # dispensing_status debe caer en 'not_applicable' (DED-30/33).
    assert prescription.lines[0].dispensing_status == medical_schemas.PrescriptionDispensingStatusEnum.not_applicable


@pytest.mark.asyncio
async def test_prescription_void_is_idempotent_guarded(db, company, patient, professional):
    consultation = await _issue_consultation(db, company, patient, professional)
    prescription = await PrescriptionService.create(
        db, company_id=company.id,
        payload=medical_schemas.PrescriptionCreate(
            consultation_id=consultation.id,
            lines=[medical_schemas.PrescriptionLineCreate(
                medication_name="Loratadina", dosage="10mg", route="oral", frequency="una vez al día", duration="10 días",
            )],
        ),
        created_by=professional.id,
    )
    voided = await PrescriptionService.void(
        db, company_id=company.id, prescription_id=prescription.id,
        payload=medical_schemas.PrescriptionVoid(void_reason="Error de transcripción"), actor_user_id=professional.id,
    )
    assert voided.voided_at is not None

    with pytest.raises(ConflictError):
        await PrescriptionService.void(
            db, company_id=company.id, prescription_id=prescription.id,
            payload=medical_schemas.PrescriptionVoid(void_reason="Doble anulación"), actor_user_id=professional.id,
        )


@pytest.mark.asyncio
async def test_prescription_list_for_patient_returns_all_issued(db, company, patient, professional):
    consultation_1 = await _issue_consultation(db, company, patient, professional)
    await PrescriptionService.create(
        db, company_id=company.id,
        payload=medical_schemas.PrescriptionCreate(
            consultation_id=consultation_1.id,
            lines=[medical_schemas.PrescriptionLineCreate(
                medication_name="Med A", dosage="1", route="oral", frequency="diario", duration="5 días",
            )],
        ),
        created_by=professional.id,
    )

    appointment_2 = await AppointmentService.create(
        db, company_id=company.id,
        payload=_appt_payload(patient.id, professional.id, _BASE + timedelta(days=1), _BASE + timedelta(days=1, minutes=30)),
        created_by=None,
    )
    consultation_2 = await ConsultationService.create(
        db, company_id=company.id,
        payload=medical_schemas.ConsultationCreate(appointment_id=appointment_2.id, diagnosis_text="Seguimiento"),
        created_by=professional.id,
    )
    await PrescriptionService.create(
        db, company_id=company.id,
        payload=medical_schemas.PrescriptionCreate(
            consultation_id=consultation_2.id,
            lines=[medical_schemas.PrescriptionLineCreate(
                medication_name="Med B", dosage="2", route="oral", frequency="diario", duration="3 días",
            )],
        ),
        created_by=professional.id,
    )

    prescriptions = await PrescriptionService.list_for_patient(
        db, company_id=company.id, patient_contact_id=patient.id, actor_user_id=professional.id
    )
    assert len(prescriptions) == 2


@pytest.mark.asyncio
async def test_prescription_requires_existing_consultation(db, company, professional):
    with pytest.raises(NotFoundError):
        await PrescriptionService.create(
            db, company_id=company.id,
            payload=medical_schemas.PrescriptionCreate(
                consultation_id=999999,
                lines=[medical_schemas.PrescriptionLineCreate(
                    medication_name="X", dosage="1", route="oral", frequency="diario", duration="1 día",
                )],
            ),
            created_by=professional.id,
        )


# ---------------------------------------------------------------------------
# Módulo 11 — Laboratorio
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_lab_order_create_with_multiple_tests(db, company, patient, professional):
    consultation = await _issue_consultation(db, company, patient, professional)
    lab_order = await LabOrderService.create(
        db, company_id=company.id,
        payload=medical_schemas.LabOrderCreate(
            consultation_id=consultation.id,
            tests=[
                medical_schemas.LabOrderTestRequest(test_name="Hemograma completo"),
                medical_schemas.LabOrderTestRequest(test_name="Glucosa"),
            ],
        ),
        created_by=professional.id,
    )
    assert len(lab_order.tests) == 2
    assert all(t.status == medical_schemas.LabOrderTestStatusEnum.pending for t in lab_order.tests)
    assert lab_order.status == medical_schemas.LabOrderStatusEnum.ordered


@pytest.mark.asyncio
async def test_lab_order_completes_when_all_tests_resulted(db, company, patient, professional):
    consultation = await _issue_consultation(db, company, patient, professional)
    lab_order = await LabOrderService.create(
        db, company_id=company.id,
        payload=medical_schemas.LabOrderCreate(
            consultation_id=consultation.id,
            tests=[
                medical_schemas.LabOrderTestRequest(test_name="Glucosa"),
                medical_schemas.LabOrderTestRequest(test_name="Colesterol"),
            ],
        ),
        created_by=professional.id,
    )
    test_ids = [t.id for t in lab_order.tests]

    await LabOrderService.enter_result(
        db, company_id=company.id, lab_order_test_id=test_ids[0],
        payload=medical_schemas.LabOrderTestResult(result_value="95", result_unit="mg/dL", reference_range_text="70-100"),
        actor_user_id=professional.id,
    )
    mid_order = await LabOrderService.get(db, company_id=company.id, lab_order_id=lab_order.id, actor_user_id=professional.id)
    assert mid_order.status == medical_schemas.LabOrderStatusEnum.ordered  # aún falta una prueba

    await LabOrderService.enter_result(
        db, company_id=company.id, lab_order_test_id=test_ids[1],
        payload=medical_schemas.LabOrderTestResult(
            result_value="280", result_unit="mg/dL", reference_range_text="<200", is_critical=True,
        ),
        actor_user_id=professional.id,
    )
    final_order = await LabOrderService.get(db, company_id=company.id, lab_order_id=lab_order.id, actor_user_id=professional.id)
    assert final_order.status == medical_schemas.LabOrderStatusEnum.completed
    critical_test = next(t for t in final_order.tests if t.test_name == "Colesterol")
    assert critical_test.is_critical is True
    assert critical_test.status == medical_schemas.LabOrderTestStatusEnum.resulted


@pytest.mark.asyncio
async def test_lab_order_test_result_cannot_be_entered_twice(db, company, patient, professional):
    consultation = await _issue_consultation(db, company, patient, professional)
    lab_order = await LabOrderService.create(
        db, company_id=company.id,
        payload=medical_schemas.LabOrderCreate(consultation_id=consultation.id, tests=[
            medical_schemas.LabOrderTestRequest(test_name="Creatinina"),
        ]),
        created_by=professional.id,
    )
    test_id = lab_order.tests[0].id
    await LabOrderService.enter_result(
        db, company_id=company.id, lab_order_test_id=test_id,
        payload=medical_schemas.LabOrderTestResult(result_value="1.0", result_unit="mg/dL"),
        actor_user_id=professional.id,
    )
    with pytest.raises(ConflictError):
        await LabOrderService.enter_result(
            db, company_id=company.id, lab_order_test_id=test_id,
            payload=medical_schemas.LabOrderTestResult(result_value="1.2", result_unit="mg/dL"),
            actor_user_id=professional.id,
        )


@pytest.mark.asyncio
async def test_lab_order_attachment_round_trip(db, company, patient, professional, tmp_path, monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "attachment_storage_root", str(tmp_path))

    consultation = await _issue_consultation(db, company, patient, professional)
    lab_order = await LabOrderService.create(
        db, company_id=company.id,
        payload=medical_schemas.LabOrderCreate(consultation_id=consultation.id, tests=[
            medical_schemas.LabOrderTestRequest(test_name="Radiografía de tórax"),
        ]),
        created_by=professional.id,
    )
    test_id = lab_order.tests[0].id

    attachment = await LabOrderService.add_attachment(
        db, company_id=company.id, lab_order_test_id=test_id,
        filename="resultado.pdf", mime_type="application/pdf", content=b"%PDF-1.4 contenido de prueba",
        uploaded_by=professional.id,
    )
    assert attachment.filename == "resultado.pdf"

    attachments = await LabOrderService.list_attachments(db, company_id=company.id, lab_order_test_id=test_id)
    assert len(attachments) == 1
    assert attachments[0].id == attachment.id

    from app.core.services import AttachmentService

    raw = AttachmentService.read_bytes(attachment)
    assert raw == b"%PDF-1.4 contenido de prueba"


@pytest.mark.asyncio
async def test_lab_order_requires_existing_consultation(db, company, professional):
    with pytest.raises(NotFoundError):
        await LabOrderService.create(
            db, company_id=company.id,
            payload=medical_schemas.LabOrderCreate(consultation_id=999999, tests=[
                medical_schemas.LabOrderTestRequest(test_name="X"),
            ]),
            created_by=professional.id,
        )


# ---------------------------------------------------------------------------------
# Módulo 12 — Teleconsulta
# ---------------------------------------------------------------------------------------------------------
class _FakeTeleconsultationProvider:
    def __init__(self):
        self.created_rooms: list[int] = []
        self.ended_rooms: list[str] = []

    async def create_room(self, *, appointment_id: int):
        self.created_rooms.append(appointment_id)
        return f"fake-room-{appointment_id}", f"https://fake.test/room/{appointment_id}"

    async def end_room(self, *, room_external_id: str) -> None:
        self.ended_rooms.append(room_external_id)


@pytest.mark.asyncio
async def test_teleconsultation_create_generates_join_url(db, company, patient, professional):
    appointment = await AppointmentService.create(
        db, company_id=company.id,
        payload=_appt_payload(patient.id, professional.id, _BASE, _BASE + timedelta(minutes=30)),
        created_by=None,
    )
    session = await TeleconsultationService.create(
        db, company_id=company.id,
        payload=medical_schemas.TeleconsultationSessionCreate(appointment_id=appointment.id),
        created_by=professional.id,
    )
    assert session.status == "scheduled"
    assert session.join_url
    assert session.patient_contact_id == patient.id


@pytest.mark.asyncio
async def test_teleconsultation_uses_injected_provider_not_real_one(db, company, patient, professional):
    appointment = await AppointmentService.create(
        db, company_id=company.id,
        payload=_appt_payload(patient.id, professional.id, _BASE, _BASE + timedelta(minutes=30)),
        created_by=None,
    )
    fake_provider = _FakeTeleconsultationProvider()
    session = await TeleconsultationService.create(
        db, company_id=company.id,
        payload=medical_schemas.TeleconsultationSessionCreate(appointment_id=appointment.id),
        created_by=professional.id, provider=fake_provider,
    )
    assert fake_provider.created_rooms == [appointment.id]
    assert session.join_url == f"https://fake.test/room/{appointment.id}"


@pytest.mark.asyncio
async def test_teleconsultation_only_one_active_per_appointment(db, company, patient, professional):
    appointment = await AppointmentService.create(
        db, company_id=company.id,
        payload=_appt_payload(patient.id, professional.id, _BASE, _BASE + timedelta(minutes=30)),
        created_by=None,
    )
    await TeleconsultationService.create(
        db, company_id=company.id,
        payload=medical_schemas.TeleconsultationSessionCreate(appointment_id=appointment.id),
        created_by=professional.id,
    )
    with pytest.raises(ConflictError):
        await TeleconsultationService.create(
            db, company_id=company.id,
            payload=medical_schemas.TeleconsultationSessionCreate(appointment_id=appointment.id),
            created_by=professional.id,
        )


@pytest.mark.asyncio
async def test_teleconsultation_cannot_create_for_cancelled_appointment(db, company, patient, professional):
    appointment = await AppointmentService.create(
        db, company_id=company.id,
        payload=_appt_payload(patient.id, professional.id, _BASE, _BASE + timedelta(minutes=30)),
        created_by=None,
    )
    await AppointmentService.cancel(
        db, company_id=company.id, appointment_id=appointment.id,
        payload=medical_schemas.AppointmentCancel(cancellation_reason="No asistió"),
    )
    with pytest.raises(ConflictError):
        await TeleconsultationService.create(
            db, company_id=company.id,
            payload=medical_schemas.TeleconsultationSessionCreate(appointment_id=appointment.id),
            created_by=professional.id,
        )


@pytest.mark.asyncio
async def test_teleconsultation_start_and_end_lifecycle(db, company, patient, professional):
    appointment = await AppointmentService.create(
        db, company_id=company.id,
        payload=_appt_payload(patient.id, professional.id, _BASE, _BASE + timedelta(minutes=30)),
        created_by=None,
    )
    session = await TeleconsultationService.create(
        db, company_id=company.id,
        payload=medical_schemas.TeleconsultationSessionCreate(appointment_id=appointment.id),
        created_by=professional.id,
    )
    started = await TeleconsultationService.start(db, company_id=company.id, session_id=session.id)
    assert started.status == "active"
    assert started.started_at is not None

    fake_provider = _FakeTeleconsultationProvider()
    ended = await TeleconsultationService.end(db, company_id=company.id, session_id=session.id, provider=fake_provider)
    assert ended.status == "ended"
    assert ended.ended_at is not None
    assert fake_provider.ended_rooms == [session.room_external_id]

    with pytest.raises(ConflictError):
        await TeleconsultationService.end(db, company_id=company.id, session_id=session.id)


@pytest.mark.asyncio
async def test_teleconsultation_get_by_appointment_returns_latest(db, company, patient, professional):
    appointment = await AppointmentService.create(
        db, company_id=company.id,
        payload=_appt_payload(patient.id, professional.id, _BASE, _BASE + timedelta(minutes=30)),
        created_by=None,
    )
    assert await TeleconsultationService.get_by_appointment(db, company_id=company.id, appointment_id=appointment.id) is None

    session = await TeleconsultationService.create(
        db, company_id=company.id,
        payload=medical_schemas.TeleconsultationSessionCreate(appointment_id=appointment.id),
        created_by=professional.id,
    )
    found = await TeleconsultationService.get_by_appointment(db, company_id=company.id, appointment_id=appointment.id)
    assert found is not None
    assert found.id == session.id


# ---------------------------------------------------------------------------
# Módulo 13 — Facturación Médica Básica
# ---------------------------------------------------------------------------
async def _setup_sales_invoice_account_mappings(db, company):
    """Fixture mínima real del motor de asientos — no existe ningún seed
    automático de plan de cuentas en el proyecto (spec DED-10: nunca se
    hardcodea una cuenta), así que se crea acá explícitamente, igual que
    tendría que hacerlo cualquier cliente nuevo antes de facturar."""
    from app.accounting import models as accounting_models

    accounts = {}
    for role, name in [("receivable", "Cuentas por Cobrar"), ("income", "Ingresos"), ("tax", "Impuestos por Pagar")]:
        account = accounting_models.Account(
            company_id=company.id, code=f"TEST-{role}", name=name, account_type=role,
        )
        db.add(account)
        await db.flush()
        accounts[role] = account
        db.add(accounting_models.DocumentAccountMapping(
            company_id=company.id, document_type="sales_invoice", role=role, account_id=account.id,
        ))
    await db.commit()
    return accounts


@pytest.mark.asyncio
async def test_billing_simple_receipt_when_administrative_inactive(db, company, patient, professional):
    consultation = await _issue_consultation(db, company, patient, professional)
    record = await MedicalBillingService.create(
        db, company_id=company.id,
        payload=medical_schemas.MedicalBillingCreate(
            consultation_id=consultation.id, amount=Decimal("500.00"), issue_date=date.today(),
        ),
        created_by=professional.id,
    )
    assert record.billing_mode == "simple_receipt"
    assert record.receipt_number is not None
    assert record.invoice_id is None
    assert record.status == "issued"


@pytest.mark.asyncio
async def test_billing_creates_real_invoice_when_administrative_active(db, company, patient, professional):
    db.add(core_models.CompanyPackage(company_id=company.id, package="administrative", status="active"))
    await db.commit()
    await _setup_sales_invoice_account_mappings(db, company)

    # El paciente debe tener is_customer=true para poder facturarlo — el
    # propio InvoiceService.create_draft ya lo exige (DED-42), no es una
    # regla nueva de medical.
    patient.is_customer = True
    await db.commit()

    consultation = await _issue_consultation(db, company, patient, professional)
    record = await MedicalBillingService.create(
        db, company_id=company.id,
        payload=medical_schemas.MedicalBillingCreate(
            consultation_id=consultation.id, amount=Decimal("750.00"), issue_date=date.today(),
        ),
        created_by=professional.id,
    )
    assert record.billing_mode == "accounting_invoice"
    assert record.invoice_id is not None
    assert record.receipt_number is None

    from app.accounting.services import InvoiceService

    invoice = await InvoiceService.get(db, company_id=company.id, invoice_id=record.invoice_id)
    assert invoice.status == "posted"
    assert invoice.total == Decimal("750.00")
    assert invoice.journal_entry_id is not None


@pytest.mark.asyncio
async def test_billing_rejects_second_active_record_for_same_consultation(db, company, patient, professional):
    consultation = await _issue_consultation(db, company, patient, professional)
    await MedicalBillingService.create(
        db, company_id=company.id,
        payload=medical_schemas.MedicalBillingCreate(consultation_id=consultation.id, amount=Decimal("300"), issue_date=date.today()),
        created_by=professional.id,
    )
    with pytest.raises(ConflictError):
        await MedicalBillingService.create(
            db, company_id=company.id,
            payload=medical_schemas.MedicalBillingCreate(consultation_id=consultation.id, amount=Decimal("300"), issue_date=date.today()),
            created_by=professional.id,
        )


@pytest.mark.asyncio
async def test_billing_cancel_then_rebill_allowed(db, company, patient, professional):
    consultation = await _issue_consultation(db, company, patient, professional)
    record = await MedicalBillingService.create(
        db, company_id=company.id,
        payload=medical_schemas.MedicalBillingCreate(consultation_id=consultation.id, amount=Decimal("300"), issue_date=date.today()),
        created_by=professional.id,
    )
    cancelled = await MedicalBillingService.cancel(
        db, company_id=company.id, record_id=record.id,
        payload=medical_schemas.MedicalBillingCancel(cancel_reason="Monto incorrecto"), actor_id=professional.id,
    )
    assert cancelled.status == "cancelled"

    with pytest.raises(ConflictError):
        await MedicalBillingService.cancel(
            db, company_id=company.id, record_id=record.id,
            payload=medical_schemas.MedicalBillingCancel(cancel_reason="Doble anulación"), actor_id=professional.id,
        )

    # Con el anterior anulado, sí se puede emitir un nuevo comprobante
    # para la misma consulta (DED-30: consulta -> 0..N comprobantes en el
    # tiempo, mismo criterio que recetas).
    new_record = await MedicalBillingService.create(
        db, company_id=company.id,
        payload=medical_schemas.MedicalBillingCreate(consultation_id=consultation.id, amount=Decimal("300"), issue_date=date.today()),
        created_by=professional.id,
    )
    assert new_record.id != record.id


@pytest.mark.asyncio
async def test_billing_requires_existing_consultation(db, company, professional):
    with pytest.raises(NotFoundError):
        await MedicalBillingService.create(
            db, company_id=company.id,
            payload=medical_schemas.MedicalBillingCreate(consultation_id=999999, amount=Decimal("100"), issue_date=date.today()),
            created_by=professional.id,
        )


# ---------------------------------------------------------------------------
# Módulo 14 — Portal / Mensajería Paciente-Médico
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_message_professional_to_patient_no_notification(db, company, patient, professional):
    message = await PatientMessageService.send(
        db, company_id=company.id,
        payload=medical_schemas.PatientMessageCreate(
            patient_contact_id=patient.id, professional_user_id=professional.id,
            sender_role=medical_schemas.PatientMessageSenderRoleEnum.professional,
            body="Recuerde tomar el medicamento con alimentos.",
        ),
        author_user_id=professional.id,
    )
    assert message.sender_role == "professional"
    assert message.author_user_id == professional.id

    notifications = (
        await db.execute(text("SELECT count(*) FROM notifications WHERE recipient_user_id = :uid"), {"uid": professional.id})
    ).scalar_one()
    assert notifications == 0


@pytest.mark.asyncio
async def test_message_patient_to_professional_creates_notification(db, company, patient, professional):
    unique = uuid.uuid4().hex[:8]
    staff = await UserService.create_user(
        db, company_id=company.id,
        payload=core_schemas.UserCreate(email=f"staff.{unique}@test.hn", full_name="Staff Recepción", password="SuperSegura123"),
        created_by=None,
    )
    message = await PatientMessageService.send(
        db, company_id=company.id,
        payload=medical_schemas.PatientMessageCreate(
            patient_contact_id=patient.id, professional_user_id=professional.id,
            sender_role=medical_schemas.PatientMessageSenderRoleEnum.patient,
            body="Doctor, sigo con dolor después de la consulta.",
        ),
        author_user_id=staff.id,  # DED-44: quien escribe en el sistema es staff, no el paciente
    )
    assert message.sender_role == "patient"
    assert message.author_user_id == staff.id

    notifications = (
        await db.execute(
            text("SELECT title, recipient_user_id FROM notifications WHERE recipient_user_id = :uid"),
            {"uid": professional.id},
        )
    ).all()
    assert len(notifications) == 1
    assert notifications[0].title == "Nuevo mensaje de paciente"


@pytest.mark.asyncio
async def test_message_list_for_patient_ordered_and_mark_read(db, company, patient, professional):
    first = await PatientMessageService.send(
        db, company_id=company.id,
        payload=medical_schemas.PatientMessageCreate(
            patient_contact_id=patient.id, professional_user_id=professional.id,
            sender_role=medical_schemas.PatientMessageSenderRoleEnum.patient, body="Primer mensaje",
        ),
        author_user_id=professional.id,
    )
    second = await PatientMessageService.send(
        db, company_id=company.id,
        payload=medical_schemas.PatientMessageCreate(
            patient_contact_id=patient.id, professional_user_id=professional.id,
            sender_role=medical_schemas.PatientMessageSenderRoleEnum.professional, body="Segundo mensaje",
        ),
        author_user_id=professional.id,
    )
    messages = await PatientMessageService.list_for_patient(db, company_id=company.id, patient_contact_id=patient.id)
    assert [m.id for m in messages] == [first.id, second.id]
    assert first.read_at is None

    read_first = await PatientMessageService.mark_read(db, company_id=company.id, message_id=first.id)
    assert read_first.read_at is not None


@pytest.mark.asyncio
async def test_message_requires_patient_flag(db, company, professional):
    non_patient = await ContactService.create_contact(
        db, company_id=company.id, payload=contacts_schemas.ContactCreate(name="No Paciente Mensajes", is_customer=True),
        created_by=None,
    )
    with pytest.raises(ValidationError):
        await PatientMessageService.send(
            db, company_id=company.id,
            payload=medical_schemas.PatientMessageCreate(
                patient_contact_id=non_patient.id, professional_user_id=professional.id,
                sender_role=medical_schemas.PatientMessageSenderRoleEnum.professional, body="No debería enviarse",
            ),
            author_user_id=professional.id,
        )


# ---------------------------------------------------------------------------
# Módulo 15 — Reserva Pública de Citas
# ---------------------------------------------------------------------------
async def _activate_packages(db, company, *packages, status=None):
    """Inserta filas reales de `company_packages` — mismo patrón que
    `test_core_module.py::test_require_package_blocks_uncontracted_and_deactivated`."""
    status = status or core_models.PackageStatusEnum.active
    for pkg in packages:
        db.add(core_models.CompanyPackage(company_id=company.id, package=pkg, status=status))
    await db.commit()


@pytest.mark.asyncio
async def test_public_booking_creates_new_patient_contact(db, company, professional):
    await _activate_packages(db, company, "web", "medical")

    booking = await PublicBookingService.create(
        db, company_id=company.id,
        payload=medical_schemas.PublicBookingCreate(
            professional_user_id=professional.id,
            scheduled_start=_BASE, scheduled_end=_BASE + timedelta(minutes=30),
            reason="Consulta general", patient_name="Paciente Widget",
            patient_email="paciente.widget@test.hn", patient_phone=None,
        ),
    )
    assert booking.booked_via_public_widget is True
    assert booking.status == "scheduled"

    result = await db.execute(
        text("SELECT name, is_patient FROM contacts WHERE email = :e"), {"e": "paciente.widget@test.hn"}
    )
    row = result.one()
    assert row.name == "Paciente Widget"
    assert row.is_patient is True


@pytest.mark.asyncio
async def test_public_booking_reuses_existing_contact_by_email_without_clobbering_flags(db, company, professional):
    await _activate_packages(db, company, "web", "medical")

    existing = await ContactService.create_contact(
        db, company_id=company.id,
        payload=contacts_schemas.ContactCreate(name="Cliente Existente", email="cliente.existente@test.hn", is_customer=True),
        created_by=None,
    )
    assert existing.is_patient is False

    booking = await PublicBookingService.create(
        db, company_id=company.id,
        payload=medical_schemas.PublicBookingCreate(
            professional_user_id=professional.id,
            scheduled_start=_BASE, scheduled_end=_BASE + timedelta(minutes=30),
            patient_name="Nombre Distinto En El Widget", patient_email="cliente.existente@test.hn", patient_phone=None,
        ),
    )

    result = await db.execute(
        text("SELECT id, is_customer, is_patient FROM contacts WHERE email = :e"), {"e": "cliente.existente@test.hn"}
    )
    row = result.one()
    assert row.id == existing.id, "Debe reutilizar el contacto existente, no duplicarlo"
    assert row.is_customer is True, "No debe pisar el flag is_customer ya existente"
    assert row.is_patient is True, "Debe ganar is_patient sin perder los demás flags"


@pytest.mark.asyncio
async def test_public_booking_rejects_overlapping_slot(db, company, professional):
    await _activate_packages(db, company, "web", "medical")

    await PublicBookingService.create(
        db, company_id=company.id,
        payload=medical_schemas.PublicBookingCreate(
            professional_user_id=professional.id,
            scheduled_start=_BASE, scheduled_end=_BASE + timedelta(minutes=30),
            patient_name="Primer Paciente", patient_email="primero@test.hn", patient_phone=None,
        ),
    )

    with pytest.raises(ConflictError):
        await PublicBookingService.create(
            db, company_id=company.id,
            payload=medical_schemas.PublicBookingCreate(
                professional_user_id=professional.id,
                scheduled_start=_BASE + timedelta(minutes=15), scheduled_end=_BASE + timedelta(minutes=45),
                patient_name="Segundo Paciente", patient_email="segundo@test.hn", patient_phone=None,
            ),
        )


@pytest.mark.asyncio
async def test_public_booking_requires_email_or_phone(db, company, professional):
    with pytest.raises(ValueError):
        medical_schemas.PublicBookingCreate(
            professional_user_id=professional.id,
            scheduled_start=_BASE, scheduled_end=_BASE + timedelta(minutes=30),
            patient_name="Sin Contacto", patient_email=None, patient_phone=None,
        )


@pytest.mark.asyncio
async def test_public_busy_slots_filters_by_overlap_and_excludes_cancelled(db, company, patient, professional):
    scheduled = await AppointmentService.create(
        db, company_id=company.id,
        payload=_appt_payload(patient.id, professional.id, _BASE, _BASE + timedelta(minutes=30)),
        created_by=None,
    )
    cancelled = await AppointmentService.create(
        db, company_id=company.id,
        payload=_appt_payload(patient.id, professional.id, _BASE + timedelta(hours=2), _BASE + timedelta(hours=2, minutes=30)),
        created_by=None,
    )
    await AppointmentService.cancel(
        db, company_id=company.id, appointment_id=cancelled.id,
        payload=medical_schemas.AppointmentCancel(cancellation_reason="Paciente no puede asistir"),
    )

    # Fuera de rango: no debe aparecer.
    outside = await AppointmentService.create(
        db, company_id=company.id,
        payload=_appt_payload(patient.id, professional.id, _BASE + timedelta(hours=5), _BASE + timedelta(hours=5, minutes=30)),
        created_by=None,
    )

    busy = await PublicBookingService.list_busy_slots(
        db, company_id=company.id, professional_user_id=professional.id,
        date_from=_BASE - timedelta(hours=1), date_to=_BASE + timedelta(hours=3),
    )
    busy_ids = {a.id for a in busy}
    assert scheduled.id in busy_ids
    assert cancelled.id not in busy_ids, "Una cita cancelada no debería bloquear el horario en el widget público"
    assert outside.id not in busy_ids


@pytest.mark.asyncio
async def test_ensure_public_booking_active_requires_both_web_and_medical(db, company):
    with pytest.raises(PackageNotLicensedError):
        await ensure_public_booking_active(db, company_id=company.id)

    await _activate_packages(db, company, "web")
    with pytest.raises(PackageNotLicensedError):
        await ensure_public_booking_active(db, company_id=company.id)

    await _activate_packages(db, company, "medical")
    await ensure_public_booking_active(db, company_id=company.id)  # no debe lanzar


@pytest.mark.asyncio
async def test_ensure_public_booking_active_blocks_suspended(db, company):
    db.add(core_models.CompanyPackage(company_id=company.id, package="web", status=core_models.PackageStatusEnum.active))
    db.add(core_models.CompanyPackage(company_id=company.id, package="medical", status=core_models.PackageStatusEnum.suspended))
    await db.commit()

    with pytest.raises(PackageSuspendedError):
        await ensure_public_booking_active(db, company_id=company.id)
