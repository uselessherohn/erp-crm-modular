"""
Servicios de medical.

Cifrado en reposo (DED-24): `pgp_sym_encrypt`/`pgp_sym_decrypt` de
`pgcrypto`, vía `sqlalchemy.func` — no hay forma declarativa de que el ORM
cifre/descifre de forma transparente sin un `TypeDecorator` custom (fuera
de alcance de este módulo); se hace explícito acá, en el único lugar del
proyecto que toca datos cifrados, para que quede auditable.

RBAC clínico "own patients": `_professional_has_treated` (más abajo).

Auditoría: TODO acceso de lectura al expediente/consulta pasa por
`AuditService.log_event` con `correlation_id` (spec 8.2, sin excepción) —
ver `medical.record.read`/`medical.consultation.read` en cada método de
lectura.
"""
from __future__ import annotations

import uuid
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.contacts.models import Contact
from app.core.services import AttachmentService, AuditService
from app.medical import models, schemas
from app.shared.exceptions import ConflictError, NotFoundError, ValidationError


def _encrypt(value: str | None):
    if value is None:
        return None
    from sqlalchemy import func

    return func.pgp_sym_encrypt(value, settings.pgcrypto_key)


def _decrypt_col(column):
    from sqlalchemy import func

    return func.pgp_sym_decrypt(column, settings.pgcrypto_key)


async def _get_patient_or_raise(db: AsyncSession, *, company_id: int, patient_contact_id: int) -> Contact:
    result = await db.execute(select(Contact).where(Contact.company_id == company_id, Contact.id == patient_contact_id))
    contact = result.scalar_one_or_none()
    if contact is None:
        raise NotFoundError(f"Contacto {patient_contact_id} no encontrado")
    if not contact.is_patient:
        raise ValidationError(f"El contacto {patient_contact_id} no tiene el flag is_patient=true")
    return contact


async def _professional_has_treated(db: AsyncSession, *, company_id: int, professional_user_id: int, patient_contact_id: int) -> bool:
    """"own patients" (RBAC clínico) — el actor tiene al menos una cita con
    ese paciente, sin importar el estado de la cita."""
    result = await db.execute(
        select(models.Appointment.id).where(
            models.Appointment.company_id == company_id,
            models.Appointment.professional_user_id == professional_user_id,
            models.Appointment.patient_contact_id == patient_contact_id,
        ).limit(1)
    )
    return result.scalar_one_or_none() is not None


class ClinicalRecordService:
    @staticmethod
    async def create_entry(
        db: AsyncSession, *, company_id: int, payload: schemas.ClinicalRecordEntryCreate, author_user_id: int
    ) -> models.ClinicalRecordEntry:
        await _get_patient_or_raise(db, company_id=company_id, patient_contact_id=payload.patient_contact_id)

        if payload.previous_entry_id is not None:
            previous = await ClinicalRecordService.get_raw(
                db, company_id=company_id, entry_id=payload.previous_entry_id
            )
            if previous.patient_contact_id != payload.patient_contact_id:
                raise ValidationError("La entrada anterior pertenece a otro paciente")

        entry = models.ClinicalRecordEntry(
            company_id=company_id,
            patient_contact_id=payload.patient_contact_id,
            entry_type=payload.entry_type.value,
            content=_encrypt(payload.content),
            previous_entry_id=payload.previous_entry_id,
            author_user_id=author_user_id,
        )
        db.add(entry)
        await db.flush()

        await AuditService.log_event(
            db, company_id=company_id, event="medical.record.create", entity_type="clinical_record_entry",
            entity_id=entry.id, user_id=author_user_id,
        )
        await db.commit()
        return await ClinicalRecordService.get(db, company_id=company_id, entry_id=entry.id, actor_user_id=author_user_id)

    @staticmethod
    async def get_raw(db: AsyncSession, *, company_id: int, entry_id: int) -> models.ClinicalRecordEntry:
        result = await db.execute(
            select(models.ClinicalRecordEntry).where(
                models.ClinicalRecordEntry.company_id == company_id, models.ClinicalRecordEntry.id == entry_id
            )
        )
        entry = result.scalar_one_or_none()
        if entry is None:
            raise NotFoundError(f"Entrada de expediente {entry_id} no encontrada")
        return entry

    @staticmethod
    async def get(db: AsyncSession, *, company_id: int, entry_id: int, actor_user_id: int) -> schemas.ClinicalRecordEntryRead:
        stmt = select(
            models.ClinicalRecordEntry,
            _decrypt_col(models.ClinicalRecordEntry.content).label("content_plain"),
        ).where(models.ClinicalRecordEntry.company_id == company_id, models.ClinicalRecordEntry.id == entry_id)
        row = (await db.execute(stmt)).one_or_none()
        if row is None:
            raise NotFoundError(f"Entrada de expediente {entry_id} no encontrada")
        entry, content_plain = row

        await AuditService.log_event(
            db, company_id=company_id, event="medical.record.read", entity_type="clinical_record_entry",
            entity_id=entry.id, user_id=actor_user_id,
        )
        await db.commit()

        return schemas.ClinicalRecordEntryRead(
            id=entry.id, company_id=entry.company_id, patient_contact_id=entry.patient_contact_id,
            entry_type=entry.entry_type, content=content_plain, previous_entry_id=entry.previous_entry_id,
            author_user_id=entry.author_user_id, created_at=entry.created_at,
        )

    @staticmethod
    async def list_for_patient(
        db: AsyncSession, *, company_id: int, patient_contact_id: int, actor_user_id: int
    ) -> list[schemas.ClinicalRecordEntryRead]:
        await _get_patient_or_raise(db, company_id=company_id, patient_contact_id=patient_contact_id)

        stmt = select(
            models.ClinicalRecordEntry,
            _decrypt_col(models.ClinicalRecordEntry.content).label("content_plain"),
        ).where(
            models.ClinicalRecordEntry.company_id == company_id,
            models.ClinicalRecordEntry.patient_contact_id == patient_contact_id,
        ).order_by(models.ClinicalRecordEntry.created_at)
        rows = (await db.execute(stmt)).all()

        await AuditService.log_event(
            db, company_id=company_id, event="medical.record.read_list", entity_type="contact",
            entity_id=patient_contact_id, user_id=actor_user_id,
        )
        await db.commit()

        return [
            schemas.ClinicalRecordEntryRead(
                id=e.id, company_id=e.company_id, patient_contact_id=e.patient_contact_id,
                entry_type=e.entry_type, content=content_plain, previous_entry_id=e.previous_entry_id,
                author_user_id=e.author_user_id, created_at=e.created_at,
            )
            for e, content_plain in rows
        ]


class AppointmentService:
    @staticmethod
    async def create(
        db: AsyncSession, *, company_id: int, payload: schemas.AppointmentCreate, created_by: int | None
    ) -> models.Appointment:
        await _get_patient_or_raise(db, company_id=company_id, patient_contact_id=payload.patient_contact_id)

        appointment = models.Appointment(
            company_id=company_id,
            patient_contact_id=payload.patient_contact_id,
            professional_user_id=payload.professional_user_id,
            scheduled_start=payload.scheduled_start,
            scheduled_end=payload.scheduled_end,
            reason=payload.reason,
            created_by=created_by,
        )
        db.add(appointment)
        try:
            await db.flush()
        except IntegrityError as exc:
            await db.rollback()
            if "excl_appointments_professional_overlap" in str(exc.orig):
                raise ConflictError(
                    "El profesional ya tiene una cita agendada que se traslapa con este horario"
                ) from exc
            raise

        await AuditService.log_event(
            db, company_id=company_id, event="medical.appointment.create", entity_type="appointment",
            entity_id=appointment.id, user_id=created_by,
        )
        await db.commit()
        await db.refresh(appointment)
        return appointment

    @staticmethod
    async def get(db: AsyncSession, *, company_id: int, appointment_id: int) -> models.Appointment:
        result = await db.execute(
            select(models.Appointment).where(
                models.Appointment.company_id == company_id, models.Appointment.id == appointment_id
            )
        )
        appointment = result.scalar_one_or_none()
        if appointment is None:
            raise NotFoundError(f"Cita {appointment_id} no encontrada")
        return appointment

    @staticmethod
    async def list(
        db: AsyncSession, *, company_id: int, professional_user_id: int | None = None, patient_contact_id: int | None = None
    ) -> list[models.Appointment]:
        stmt = select(models.Appointment).where(models.Appointment.company_id == company_id)
        if professional_user_id is not None:
            stmt = stmt.where(models.Appointment.professional_user_id == professional_user_id)
        if patient_contact_id is not None:
            stmt = stmt.where(models.Appointment.patient_contact_id == patient_contact_id)
        result = await db.execute(stmt.order_by(models.Appointment.scheduled_start))
        return list(result.scalars().all())

    @staticmethod
    async def confirm(db: AsyncSession, *, company_id: int, appointment_id: int) -> models.Appointment:
        appointment = await AppointmentService._get_locked(db, company_id=company_id, appointment_id=appointment_id)
        if appointment.status != "scheduled":
            raise ConflictError(f"Solo una cita 'scheduled' puede confirmarse (estado actual: {appointment.status})")
        appointment.status = "confirmed"
        await db.commit()
        await db.refresh(appointment)
        return appointment

    @staticmethod
    async def reschedule(
        db: AsyncSession, *, company_id: int, appointment_id: int, payload: schemas.AppointmentReschedule
    ) -> models.Appointment:
        appointment = await AppointmentService._get_locked(db, company_id=company_id, appointment_id=appointment_id)
        if appointment.status not in ("scheduled", "confirmed"):
            raise ConflictError(f"No se puede reprogramar una cita en estado '{appointment.status}'")

        appointment.scheduled_start = payload.scheduled_start
        appointment.scheduled_end = payload.scheduled_end
        appointment.reason = f"{appointment.reason or ''} | Reprogramada: {payload.reason}".strip(" |")
        appointment.status = "scheduled"
        try:
            await db.commit()
        except IntegrityError as exc:
            await db.rollback()
            if "excl_appointments_professional_overlap" in str(exc.orig):
                raise ConflictError(
                    "El profesional ya tiene una cita agendada que se traslapa con el nuevo horario"
                ) from exc
            raise
        await db.refresh(appointment)
        return appointment

    @staticmethod
    async def cancel(
        db: AsyncSession, *, company_id: int, appointment_id: int, payload: schemas.AppointmentCancel
    ) -> models.Appointment:
        appointment = await AppointmentService._get_locked(db, company_id=company_id, appointment_id=appointment_id)
        if appointment.status in ("completed", "cancelled", "no_show"):
            raise ConflictError(f"No se puede cancelar una cita en estado '{appointment.status}'")
        appointment.status = "cancelled"
        appointment.cancellation_reason = payload.cancellation_reason
        await db.commit()
        await db.refresh(appointment)
        return appointment

    @staticmethod
    async def _get_locked(db: AsyncSession, *, company_id: int, appointment_id: int) -> models.Appointment:
        result = await db.execute(
            select(models.Appointment)
            .where(models.Appointment.company_id == company_id, models.Appointment.id == appointment_id)
            .with_for_update()
        )
        appointment = result.scalar_one_or_none()
        if appointment is None:
            raise NotFoundError(f"Cita {appointment_id} no encontrada")
        return appointment


class ConsultationService:
    @staticmethod
    async def create(
        db: AsyncSession, *, company_id: int, payload: schemas.ConsultationCreate, created_by: int
    ) -> schemas.ConsultationRead:
        appointment = await AppointmentService._get_locked(
            db, company_id=company_id, appointment_id=payload.appointment_id
        )
        if appointment.status not in ("scheduled", "confirmed"):
            raise ConflictError(
                f"No se puede registrar una consulta sobre una cita en estado '{appointment.status}'"
            )

        existing = await db.execute(
            select(models.Consultation.id).where(
                models.Consultation.appointment_id == appointment.id, models.Consultation.superseded_by_id.is_(None)
            )
        )
        if existing.scalar_one_or_none() is not None:
            raise ConflictError("Esta cita ya tiene una consulta registrada — usa el endpoint de corrección")

        consultation = models.Consultation(
            company_id=company_id,
            appointment_id=appointment.id,
            patient_contact_id=appointment.patient_contact_id,
            professional_user_id=appointment.professional_user_id,
            physical_exam=_encrypt(payload.physical_exam),
            diagnosis_cie10=payload.diagnosis_cie10,
            diagnosis_text=_encrypt(payload.diagnosis_text),
            treatment_plan=_encrypt(payload.treatment_plan),
            created_by=created_by,
        )
        db.add(consultation)
        await db.flush()

        appointment.status = "completed"

        await AuditService.log_event(
            db, company_id=company_id, event="medical.consultation.create", entity_type="consultation",
            entity_id=consultation.id, user_id=created_by,
        )
        await db.commit()
        return await ConsultationService.get(db, company_id=company_id, consultation_id=consultation.id, actor_user_id=created_by)

    @staticmethod
    async def correct(
        db: AsyncSession, *, company_id: int, consultation_id: int, payload: schemas.ConsultationCorrect, created_by: int
    ) -> schemas.ConsultationRead:
        result = await db.execute(
            select(models.Consultation)
            .where(models.Consultation.company_id == company_id, models.Consultation.id == consultation_id)
            .with_for_update()
        )
        previous = result.scalar_one_or_none()
        if previous is None:
            raise NotFoundError(f"Consulta {consultation_id} no encontrada")
        if previous.superseded_by_id is not None:
            raise ConflictError("Esta consulta ya fue corregida por una versión más reciente")

        new_consultation = models.Consultation(
            company_id=company_id,
            appointment_id=previous.appointment_id,
            patient_contact_id=previous.patient_contact_id,
            professional_user_id=previous.professional_user_id,
            physical_exam=_encrypt(payload.physical_exam),
            diagnosis_cie10=payload.diagnosis_cie10,
            diagnosis_text=_encrypt(payload.diagnosis_text),
            treatment_plan=_encrypt(payload.treatment_plan),
            previous_consultation_id=previous.id,
            created_by=created_by,
        )
        db.add(new_consultation)
        await db.flush()

        previous.superseded_by_id = new_consultation.id

        await AuditService.log_event(
            db, company_id=company_id, event="medical.consultation.correct", entity_type="consultation",
            entity_id=new_consultation.id, user_id=created_by,
        )
        await db.commit()
        return await ConsultationService.get(db, company_id=company_id, consultation_id=new_consultation.id, actor_user_id=created_by)

    @staticmethod
    async def get(db: AsyncSession, *, company_id: int, consultation_id: int, actor_user_id: int) -> schemas.ConsultationRead:
        stmt = select(
            models.Consultation,
            _decrypt_col(models.Consultation.physical_exam).label("physical_exam_plain"),
            _decrypt_col(models.Consultation.diagnosis_text).label("diagnosis_text_plain"),
            _decrypt_col(models.Consultation.treatment_plan).label("treatment_plan_plain"),
        ).where(models.Consultation.company_id == company_id, models.Consultation.id == consultation_id)
        row = (await db.execute(stmt)).one_or_none()
        if row is None:
            raise NotFoundError(f"Consulta {consultation_id} no encontrada")
        consultation, physical_exam_plain, diagnosis_text_plain, treatment_plan_plain = row

        await AuditService.log_event(
            db, company_id=company_id, event="medical.consultation.read", entity_type="consultation",
            entity_id=consultation.id, user_id=actor_user_id,
        )
        await db.commit()

        return schemas.ConsultationRead(
            id=consultation.id, company_id=consultation.company_id, appointment_id=consultation.appointment_id,
            patient_contact_id=consultation.patient_contact_id, professional_user_id=consultation.professional_user_id,
            physical_exam=physical_exam_plain, diagnosis_cie10=consultation.diagnosis_cie10,
            diagnosis_text=diagnosis_text_plain, treatment_plan=treatment_plan_plain,
            previous_consultation_id=consultation.previous_consultation_id, superseded_by_id=consultation.superseded_by_id,
            created_by=consultation.created_by, created_at=consultation.created_at,
        )


async def get_by_appointment(db: AsyncSession, *, company_id: int, appointment_id: int, actor_user_id: int) -> schemas.ConsultationRead | None:
    """Fase 3 (frontend) expuso un hueco real de Fase 2: no había forma de
    recuperar la consulta "vigente" de una cita ya completada sin conocer
    su id de antemano (el flujo normal — agendar, más tarde volver a ver
    la cita — no lo conserva). Se agrega acá, no como método de instancia
    de `ConsultationService`, porque no encaja en su forma CRUD normal."""
    result = await db.execute(
        select(models.Consultation.id).where(
            models.Consultation.company_id == company_id,
            models.Consultation.appointment_id == appointment_id,
            models.Consultation.superseded_by_id.is_(None),
        )
    )
    consultation_id = result.scalar_one_or_none()
    if consultation_id is None:
        return None
    return await ConsultationService.get(db, company_id=company_id, consultation_id=consultation_id, actor_user_id=actor_user_id)


async def professional_has_treated(db: AsyncSession, *, company_id: int, professional_user_id: int, patient_contact_id: int) -> bool:
    """Reexportado para el router (chequeo RBAC 'own patients')."""
    return await _professional_has_treated(
        db, company_id=company_id, professional_user_id=professional_user_id, patient_contact_id=patient_contact_id
    )


# ---------------------------------------------------------------------------
# Módulo 10 — Recetas. Ver DED-30/31/32/33 en models.py.
# ---------------------------------------------------------------------------
class PrescriptionService:
    @staticmethod
    async def create(
        db: AsyncSession, *, company_id: int, payload: schemas.PrescriptionCreate, created_by: int
    ) -> schemas.PrescriptionRead:
        from app.core.dependencies import get_active_packages

        consultation = await ConsultationService.get(
            db, company_id=company_id, consultation_id=payload.consultation_id, actor_user_id=created_by
        )

        active_packages = await get_active_packages(company_id, db)
        dispensing_status = (
            models.PrescriptionDispensingStatusEnum.pending.value
            if "pharmacy" in active_packages
            else models.PrescriptionDispensingStatusEnum.not_applicable.value
        )

        prescription = models.Prescription(
            company_id=company_id,
            consultation_id=consultation.id,
            patient_contact_id=consultation.patient_contact_id,
            professional_user_id=consultation.professional_user_id,
            notes=payload.notes,
            created_by=created_by,
        )
        db.add(prescription)
        await db.flush()

        for line in payload.lines:
            db.add(models.PrescriptionLine(
                company_id=company_id, prescription_id=prescription.id,
                medication_name=line.medication_name, dosage=line.dosage, route=line.route,
                frequency=line.frequency, duration=line.duration, dispensing_status=dispensing_status,
            ))

        await AuditService.log_event(
            db, company_id=company_id, event="medical.prescription.create", entity_type="prescription",
            entity_id=prescription.id, user_id=created_by,
        )
        await db.commit()
        return await PrescriptionService.get(db, company_id=company_id, prescription_id=prescription.id, actor_user_id=created_by)

    @staticmethod
    async def get(db: AsyncSession, *, company_id: int, prescription_id: int, actor_user_id: int) -> schemas.PrescriptionRead:
        result = await db.execute(
            select(models.Prescription).where(
                models.Prescription.company_id == company_id, models.Prescription.id == prescription_id
            )
        )
        prescription = result.scalar_one_or_none()
        if prescription is None:
            raise NotFoundError(f"Receta {prescription_id} no encontrada")

        lines_result = await db.execute(
            select(models.PrescriptionLine)
            .where(models.PrescriptionLine.prescription_id == prescription.id)
            .order_by(models.PrescriptionLine.id)
        )
        lines = list(lines_result.scalars().all())

        await AuditService.log_event(
            db, company_id=company_id, event="medical.prescription.read", entity_type="prescription",
            entity_id=prescription.id, user_id=actor_user_id,
        )
        await db.commit()

        return schemas.PrescriptionRead(
            id=prescription.id, company_id=prescription.company_id, consultation_id=prescription.consultation_id,
            patient_contact_id=prescription.patient_contact_id, professional_user_id=prescription.professional_user_id,
            notes=prescription.notes, voided_at=prescription.voided_at, void_reason=prescription.void_reason,
            issued_at=prescription.issued_at, created_by=prescription.created_by,
            lines=[schemas.PrescriptionLineRead.model_validate(l) for l in lines],
        )

    @staticmethod
    async def list_for_patient(
        db: AsyncSession, *, company_id: int, patient_contact_id: int, actor_user_id: int
    ) -> list[schemas.PrescriptionRead]:
        result = await db.execute(
            select(models.Prescription.id)
            .where(models.Prescription.company_id == company_id, models.Prescription.patient_contact_id == patient_contact_id)
            .order_by(models.Prescription.issued_at.desc())
        )
        ids = [row[0] for row in result.all()]
        return [await PrescriptionService.get(db, company_id=company_id, prescription_id=pid, actor_user_id=actor_user_id) for pid in ids]

    @staticmethod
    async def void(
        db: AsyncSession, *, company_id: int, prescription_id: int, payload: schemas.PrescriptionVoid, actor_user_id: int
    ) -> schemas.PrescriptionRead:
        result = await db.execute(
            select(models.Prescription)
            .where(models.Prescription.company_id == company_id, models.Prescription.id == prescription_id)
            .with_for_update()
        )
        prescription = result.scalar_one_or_none()
        if prescription is None:
            raise NotFoundError(f"Receta {prescription_id} no encontrada")
        if prescription.voided_at is not None:
            raise ConflictError("Esta receta ya fue anulada")

        from sqlalchemy import func as sa_func

        prescription.voided_at = sa_func.now()
        prescription.void_reason = payload.void_reason

        await AuditService.log_event(
            db, company_id=company_id, event="medical.prescription.void", entity_type="prescription",
            entity_id=prescription.id, user_id=actor_user_id,
        )
        await db.commit()
        return await PrescriptionService.get(db, company_id=company_id, prescription_id=prescription_id, actor_user_id=actor_user_id)


# ---------------------------------------------------------------------------
# Módulo 11 — Laboratorio. Ver DED-34/35/36 en models.py.
# ---------------------------------------------------------------------------
class LabOrderService:
    @staticmethod
    async def create(
        db: AsyncSession, *, company_id: int, payload: schemas.LabOrderCreate, created_by: int
    ) -> schemas.LabOrderRead:
        consultation = await ConsultationService.get(
            db, company_id=company_id, consultation_id=payload.consultation_id, actor_user_id=created_by
        )

        lab_order = models.LabOrder(
            company_id=company_id, consultation_id=consultation.id,
            patient_contact_id=consultation.patient_contact_id, professional_user_id=consultation.professional_user_id,
            created_by=created_by,
        )
        db.add(lab_order)
        await db.flush()

        for test in payload.tests:
            db.add(models.LabOrderTest(
                company_id=company_id, lab_order_id=lab_order.id, test_name=test.test_name,
            ))

        await AuditService.log_event(
            db, company_id=company_id, event="medical.lab_order.create", entity_type="lab_order",
            entity_id=lab_order.id, user_id=created_by,
        )
        await db.commit()
        return await LabOrderService.get(db, company_id=company_id, lab_order_id=lab_order.id, actor_user_id=created_by)

    @staticmethod
    async def get(db: AsyncSession, *, company_id: int, lab_order_id: int, actor_user_id: int) -> schemas.LabOrderRead:
        result = await db.execute(
            select(models.LabOrder).where(models.LabOrder.company_id == company_id, models.LabOrder.id == lab_order_id)
        )
        lab_order = result.scalar_one_or_none()
        if lab_order is None:
            raise NotFoundError(f"Orden de laboratorio {lab_order_id} no encontrada")

        tests_result = await db.execute(
            select(models.LabOrderTest)
            .where(models.LabOrderTest.lab_order_id == lab_order.id)
            .order_by(models.LabOrderTest.id)
        )
        tests = list(tests_result.scalars().all())

        await AuditService.log_event(
            db, company_id=company_id, event="medical.lab_order.read", entity_type="lab_order",
            entity_id=lab_order.id, user_id=actor_user_id,
        )
        await db.commit()

        return schemas.LabOrderRead(
            id=lab_order.id, company_id=lab_order.company_id, consultation_id=lab_order.consultation_id,
            patient_contact_id=lab_order.patient_contact_id, professional_user_id=lab_order.professional_user_id,
            status=lab_order.status, ordered_at=lab_order.ordered_at, created_by=lab_order.created_by,
            tests=[schemas.LabOrderTestRead.model_validate(t) for t in tests],
        )

    @staticmethod
    async def list_for_patient(
        db: AsyncSession, *, company_id: int, patient_contact_id: int, actor_user_id: int
    ) -> list[schemas.LabOrderRead]:
        result = await db.execute(
            select(models.LabOrder.id)
            .where(models.LabOrder.company_id == company_id, models.LabOrder.patient_contact_id == patient_contact_id)
            .order_by(models.LabOrder.ordered_at.desc())
        )
        ids = [row[0] for row in result.all()]
        return [await LabOrderService.get(db, company_id=company_id, lab_order_id=oid, actor_user_id=actor_user_id) for oid in ids]

    @staticmethod
    async def enter_result(
        db: AsyncSession, *, company_id: int, lab_order_test_id: int, payload: schemas.LabOrderTestResult, actor_user_id: int
    ) -> models.LabOrderTest:
        from sqlalchemy import func as sa_func

        result = await db.execute(
            select(models.LabOrderTest)
            .where(models.LabOrderTest.company_id == company_id, models.LabOrderTest.id == lab_order_test_id)
            .with_for_update()
        )
        test = result.scalar_one_or_none()
        if test is None:
            raise NotFoundError(f"Prueba de laboratorio {lab_order_test_id} no encontrada")
        if test.status == "resulted":
            raise ConflictError("Esta prueba ya tiene un resultado cargado")

        test.result_value = payload.result_value
        test.result_unit = payload.result_unit
        test.reference_range_text = payload.reference_range_text
        test.is_critical = payload.is_critical
        test.status = "resulted"
        test.resulted_at = sa_func.now()
        test.resulted_by = actor_user_id
        await db.flush()

        # Si todas las pruebas de la orden ya tienen resultado, la orden
        # pasa a 'completed' — transición derivada, no pedida por el actor.
        siblings = await db.execute(
            select(models.LabOrderTest.status).where(models.LabOrderTest.lab_order_id == test.lab_order_id)
        )
        statuses = [row[0] for row in siblings.all()]
        if all(s == "resulted" for s in statuses):
            order_result = await db.execute(
                select(models.LabOrder).where(models.LabOrder.id == test.lab_order_id).with_for_update()
            )
            order = order_result.scalar_one()
            order.status = "completed"

        await AuditService.log_event(
            db, company_id=company_id, event="medical.lab_order_test.result", entity_type="lab_order_test",
            entity_id=test.id, user_id=actor_user_id,
        )
        await db.commit()
        await db.refresh(test)
        return test

    @staticmethod
    async def add_attachment(
        db: AsyncSession, *, company_id: int, lab_order_test_id: int, filename: str, mime_type: str,
        content: bytes, uploaded_by: int,
    ):
        test_result = await db.execute(
            select(models.LabOrderTest.id).where(
                models.LabOrderTest.company_id == company_id, models.LabOrderTest.id == lab_order_test_id
            )
        )
        if test_result.scalar_one_or_none() is None:
            raise NotFoundError(f"Prueba de laboratorio {lab_order_test_id} no encontrada")

        attachment = await AttachmentService.store(
            db, company_id=company_id, entity_type="lab_order_test", entity_id=lab_order_test_id,
            filename=filename, mime_type=mime_type, content=content, uploaded_by=uploaded_by,
        )
        await AuditService.log_event(
            db, company_id=company_id, event="medical.lab_order_test.attachment_upload", entity_type="lab_order_test",
            entity_id=lab_order_test_id, user_id=uploaded_by,
        )
        await db.commit()
        return attachment

    @staticmethod
    async def list_attachments(db: AsyncSession, *, company_id: int, lab_order_test_id: int):
        return await AttachmentService.list_for_entity(
            db, company_id=company_id, entity_type="lab_order_test", entity_id=lab_order_test_id
        )


# ---------------------------------------------------------------------------------
# Módulo 12 — Teleconsulta. Ver DED-37/38/39 en models.py.
# ---------------------------------------------------------------------------------------------
import abc


class TeleconsultationProvider(abc.ABC):
    @abc.abstractmethod
    async def create_room(self, *, appointment_id: int) -> tuple[str, str]:
        """Devuelve (room_external_id, join_url)."""
        raise NotImplementedError

    @abc.abstractmethod
    async def end_room(self, *, room_external_id: str) -> None:
        raise NotImplementedError


class DevStubTeleconsultationProvider(TeleconsultationProvider):
    """Implementación de desarrollo (DED-37) — el sandbox de este proyecto
    no tiene salida de red hacia Twilio/Daily/etc. Genera una URL de sala
    local determinística, sin llamar a ningún proveedor real. Producción
    inyecta un cliente real detrás de la misma interfaz."""

    async def create_room(self, *, appointment_id: int) -> tuple[str, str]:
        room_id = f"dev-{uuid.uuid4().hex}"
        return room_id, f"https://teleconsulta.local/dev-room/{room_id}?appointment={appointment_id}"

    async def end_room(self, *, room_external_id: str) -> None:
        return None


_default_teleconsultation_provider: TeleconsultationProvider = DevStubTeleconsultationProvider()


class TeleconsultationService:
    @staticmethod
    async def create(
        db: AsyncSession, *, company_id: int, payload: schemas.TeleconsultationSessionCreate, created_by: int,
        provider: TeleconsultationProvider | None = None,
    ) -> models.TeleconsultationSession:
        appointment = await AppointmentService._get_locked(
            db, company_id=company_id, appointment_id=payload.appointment_id
        )
        if appointment.status not in ("scheduled", "confirmed"):
            raise ConflictError(
                f"No se puede abrir una sala de teleconsulta para una cita en estado '{appointment.status}'"
            )

        existing = await db.execute(
            select(models.TeleconsultationSession.id).where(
                models.TeleconsultationSession.appointment_id == appointment.id,
                models.TeleconsultationSession.status.in_(("scheduled", "active")),
            )
        )
        if existing.scalar_one_or_none() is not None:
            raise ConflictError("Esta cita ya tiene una sesión de teleconsulta activa")

        active_provider = provider or _default_teleconsultation_provider
        room_external_id, join_url = await active_provider.create_room(appointment_id=appointment.id)

        session = models.TeleconsultationSession(
            company_id=company_id, appointment_id=appointment.id,
            patient_contact_id=appointment.patient_contact_id, professional_user_id=appointment.professional_user_id,
            provider=active_provider.__class__.__name__, room_external_id=room_external_id, join_url=join_url,
            created_by=created_by,
        )
        db.add(session)
        await db.flush()

        await AuditService.log_event(
            db, company_id=company_id, event="medical.teleconsultation.create", entity_type="teleconsultation_session",
            entity_id=session.id, user_id=created_by,
        )
        await db.commit()
        await db.refresh(session)
        return session

    @staticmethod
    async def get(db: AsyncSession, *, company_id: int, session_id: int) -> models.TeleconsultationSession:
        result = await db.execute(
            select(models.TeleconsultationSession).where(
                models.TeleconsultationSession.company_id == company_id, models.TeleconsultationSession.id == session_id
            )
        )
        session = result.scalar_one_or_none()
        if session is None:
            raise NotFoundError(f"Sesión de teleconsulta {session_id} no encontrada")
        return session

    @staticmethod
    async def get_by_appointment(db: AsyncSession, *, company_id: int, appointment_id: int) -> models.TeleconsultationSession | None:
        result = await db.execute(
            select(models.TeleconsultationSession).where(
                models.TeleconsultationSession.company_id == company_id,
                models.TeleconsultationSession.appointment_id == appointment_id,
                models.TeleconsultationSession.status.in_(("scheduled", "active", "ended")),
            ).order_by(models.TeleconsultationSession.created_at.desc())
        )
        return result.scalars().first()

    @staticmethod
    async def start(db: AsyncSession, *, company_id: int, session_id: int) -> models.TeleconsultationSession:
        result = await db.execute(
            select(models.TeleconsultationSession)
            .where(models.TeleconsultationSession.company_id == company_id, models.TeleconsultationSession.id == session_id)
            .with_for_update()
        )
        session = result.scalar_one_or_none()
        if session is None:
            raise NotFoundError(f"Sesión de teleconsulta {session_id} no encontrada")
        if session.status != "scheduled":
            raise ConflictError(f"Solo una sesión 'scheduled' puede iniciarse (estado actual: {session.status})")

        from sqlalchemy import func as sa_func

        session.status = "active"
        session.started_at = sa_func.now()
        await db.commit()
        await db.refresh(session)
        return session

    @staticmethod
    async def end(
        db: AsyncSession, *, company_id: int, session_id: int, provider: TeleconsultationProvider | None = None
    ) -> models.TeleconsultationSession:
        result = await db.execute(
            select(models.TeleconsultationSession)
            .where(models.TeleconsultationSession.company_id == company_id, models.TeleconsultationSession.id == session_id)
            .with_for_update()
        )
        session = result.scalar_one_or_none()
        if session is None:
            raise NotFoundError(f"Sesión de teleconsulta {session_id} no encontrada")
        if session.status not in ("scheduled", "active"):
            raise ConflictError(f"No se puede finalizar una sesión en estado '{session.status}'")

        active_provider = provider or _default_teleconsultation_provider
        await active_provider.end_room(room_external_id=session.room_external_id)

        from sqlalchemy import func as sa_func

        session.status = "ended"
        session.ended_at = sa_func.now()
        await db.commit()
        await db.refresh(session)
        return session


# ---------------------------------------------------------------------------------
# Módulo 13 — Facturación Médica Básica. Ver DED-40/41/42 en models.py.
# ---------------------------------------------------------------------------
class MedicalBillingService:
    @staticmethod
    async def create(
        db: AsyncSession, *, company_id: int, payload: schemas.MedicalBillingCreate, created_by: int
    ) -> models.MedicalBillingRecord:
        from app.core.dependencies import get_active_packages
        from app.core.services import DocumentNumberingService

        consultation = await ConsultationService.get(
            db, company_id=company_id, consultation_id=payload.consultation_id, actor_user_id=created_by
        )

        existing = await db.execute(
            select(models.MedicalBillingRecord.id).where(
                models.MedicalBillingRecord.consultation_id == consultation.id,
                models.MedicalBillingRecord.status == "issued",
            )
        )
        if existing.scalar_one_or_none() is not None:
            raise ConflictError("Esta consulta ya tiene un comprobante de facturación vigente")

        active_packages = await get_active_packages(company_id, db)

        invoice_id = None
        receipt_number = None

        if "administrative" in active_packages:
            # DED-40/42: 'administrative' activo -> se usa el motor de
            # asientos real, no se duplica lógica de facturación acá.
            from app.accounting import schemas as accounting_schemas
            from app.accounting.services import InvoiceService

            invoice = await InvoiceService.create_draft(
                db, company_id=company_id,
                payload=accounting_schemas.InvoiceCreate(
                    direction=accounting_schemas.DirectionEnum.sale,
                    contact_id=consultation.patient_contact_id,
                    currency_code=payload.currency_code,
                    issue_date=payload.issue_date,
                    source_document_type="medical_consultation",
                    source_document_id=consultation.id,
                    lines=[accounting_schemas.InvoiceLineCreate(
                        description="Consulta médica", quantity=Decimal("1"),
                        unit_price=payload.amount, tax_rate_id=payload.tax_rate_id,
                    )],
                ),
                created_by=created_by,
            )
            invoice = await InvoiceService.post(db, company_id=company_id, invoice_id=invoice.id, actor_id=created_by)
            invoice_id = invoice.id
            billing_mode = "accounting_invoice"
        else:
            receipt_number = await DocumentNumberingService.next_number(
                db, company_id=company_id, doc_type="medical_receipt", prefix="REC",
                year=payload.issue_date.year,
            )
            billing_mode = "simple_receipt"

        record = models.MedicalBillingRecord(
            company_id=company_id, consultation_id=consultation.id,
            patient_contact_id=consultation.patient_contact_id, professional_user_id=consultation.professional_user_id,
            billing_mode=billing_mode, amount=payload.amount, currency_code=payload.currency_code,
            issue_date=payload.issue_date, invoice_id=invoice_id, receipt_number=receipt_number,
            created_by=created_by,
        )
        db.add(record)
        await db.flush()

        await AuditService.log_event(
            db, company_id=company_id, event="medical.billing.create", entity_type="medical_billing_record",
            entity_id=record.id, user_id=created_by,
        )
        await db.commit()
        await db.refresh(record)
        return record

    @staticmethod
    async def get_for_consultation(
        db: AsyncSession, *, company_id: int, consultation_id: int
    ) -> models.MedicalBillingRecord | None:
        result = await db.execute(
            select(models.MedicalBillingRecord).where(
                models.MedicalBillingRecord.company_id == company_id,
                models.MedicalBillingRecord.consultation_id == consultation_id,
            ).order_by(models.MedicalBillingRecord.created_at.desc())
        )
        return result.scalars().first()

    @staticmethod
    async def cancel(
        db: AsyncSession, *, company_id: int, record_id: int, payload: schemas.MedicalBillingCancel, actor_id: int
    ) -> models.MedicalBillingRecord:
        result = await db.execute(
            select(models.MedicalBillingRecord)
            .where(models.MedicalBillingRecord.company_id == company_id, models.MedicalBillingRecord.id == record_id)
            .with_for_update()
        )
        record = result.scalar_one_or_none()
        if record is None:
            raise NotFoundError(f"Comprobante {record_id} no encontrado")
        if record.status == "cancelled":
            raise ConflictError("Este comprobante ya fue anulado")

        from sqlalchemy import func as sa_func

        record.status = "cancelled"
        record.cancelled_at = sa_func.now()
        record.cancel_reason = payload.cancel_reason

        await AuditService.log_event(
            db, company_id=company_id, event="medical.billing.cancel", entity_type="medical_billing_record",
            entity_id=record.id, user_id=actor_id,
        )
        await db.commit()
        await db.refresh(record)
        return record


# ---------------------------------------------------------------------------
# Módulo 14 — Portal / Mensajería Paciente-Médico. Ver DED-43/44 arriba.
# ---------------------------------------------------------------------------
class PatientMessageService:
    @staticmethod
    async def send(
        db: AsyncSession, *, company_id: int, payload: schemas.PatientMessageCreate, author_user_id: int
    ) -> models.PatientMessage:
        patient = await _get_patient_or_raise(db, company_id=company_id, patient_contact_id=payload.patient_contact_id)

        message = models.PatientMessage(
            company_id=company_id, patient_contact_id=patient.id,
            professional_user_id=payload.professional_user_id, sender_role=payload.sender_role.value,
            author_user_id=author_user_id, body=payload.body,
        )
        db.add(message)
        await db.flush()

        await AuditService.log_event(
            db, company_id=company_id, event="medical.message.send", entity_type="patient_message",
            entity_id=message.id, user_id=author_user_id,
        )

        if payload.sender_role.value == "patient":
            # DED-43: notifications es Transversal en este proyecto (sin
            # require_package) — siempre disponible, se notifica siempre
            # al profesional tratante, no hay rama condicional.
            from app.notifications import schemas as notifications_schemas
            from app.notifications.services import NotificationService

            await NotificationService.send(
                db, company_id=company_id,
                payload=notifications_schemas.NotificationSend(
                    recipient_user_id=payload.professional_user_id,
                    title="Nuevo mensaje de paciente",
                    body=f"{patient.name}: {payload.body[:200]}",
                ),
            )

        await db.commit()
        await db.refresh(message)
        return message

    @staticmethod
    async def list_for_patient(db: AsyncSession, *, company_id: int, patient_contact_id: int) -> list[models.PatientMessage]:
        result = await db.execute(
            select(models.PatientMessage)
            .where(models.PatientMessage.company_id == company_id, models.PatientMessage.patient_contact_id == patient_contact_id)
            .order_by(models.PatientMessage.created_at)
        )
        return list(result.scalars().all())

    @staticmethod
    async def mark_read(db: AsyncSession, *, company_id: int, message_id: int) -> models.PatientMessage:
        result = await db.execute(
            select(models.PatientMessage).where(
                models.PatientMessage.company_id == company_id, models.PatientMessage.id == message_id
            )
        )
        message = result.scalar_one_or_none()
        if message is None:
            raise NotFoundError(f"Mensaje {message_id} no encontrado")
        if message.read_at is None:
            from sqlalchemy import func as sa_func

            message.read_at = sa_func.now()
            await db.commit()
            await db.refresh(message)
        return message
