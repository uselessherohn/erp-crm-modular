"""
Routers de medical. Todas las rutas exigen el paquete `medical` activo
(`require_package`, spec 2.4) además del permiso RBAC puntual.

RBAC clínico "own patients" vs "read-all" (spec 8.2): implementado como
chequeo explícito en el router — `medical:record:read-all`/
`medical:consultation:read-all` pasa siempre; sin ese permiso, se exige
`medical:record:read-own-patients`/`medical:consultation:read-own-patients`
Y que el actor haya tratado a ese paciente (`professional_has_treated`).
Ninguno de los dos alcanza solo, a diferencia de un permiso RBAC plano —
mismo patrón regulatorio que `hr:employee:read-sensitive`, pero con una
condición de datos además del permiso.
"""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, File, UploadFile
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import (
    get_current_company_id,
    get_current_user,
    get_db_with_tenant_context,
    require_package,
    require_permission,
    user_has_permission,
)
from app.core.models import User
from app.core.services import AttachmentService
from app.medical import models as medical_models
from app.medical import schemas
from app.medical.dependencies import ensure_public_booking_active, get_public_db_context
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
    get_by_appointment,
    professional_has_treated,
)
from app.shared.exceptions import NotFoundError, PermissionDeniedError

router = APIRouter(prefix="/medical", tags=["medical"], dependencies=[Depends(require_package("medical"))])


async def _require_clinical_read(
    db: AsyncSession, *, actor: User, patient_contact_id: int, all_permission: str, own_permission: str
) -> None:
    if await user_has_permission(db, user_id=actor.id, code=all_permission):
        return
    if await user_has_permission(db, user_id=actor.id, code=own_permission) and await professional_has_treated(
        db, company_id=actor.company_id, professional_user_id=actor.id, patient_contact_id=patient_contact_id
    ):
        return
    raise PermissionDeniedError(
        f"Requiere '{all_permission}', o '{own_permission}' sobre un paciente que el actor haya tratado"
    )


# ---------------------------------------------------------------------------
# Expediente Clínico
# ---------------------------------------------------------------------------
@router.post("/records", response_model=schemas.ClinicalRecordEntryRead, status_code=201)
async def create_record_entry(
    payload: schemas.ClinicalRecordEntryCreate,
    company_id: int = Depends(get_current_company_id),
    db: AsyncSession = Depends(get_db_with_tenant_context),
    actor: User = Depends(require_permission("medical:record:create")),
) -> schemas.ClinicalRecordEntryRead:
    entry = await ClinicalRecordService.create_entry(db, company_id=company_id, payload=payload, author_user_id=actor.id)
    return schemas.ClinicalRecordEntryRead(
        id=entry.id, company_id=entry.company_id, patient_contact_id=entry.patient_contact_id,
        entry_type=entry.entry_type, content=payload.content, previous_entry_id=entry.previous_entry_id,
        author_user_id=entry.author_user_id, created_at=entry.created_at,
    )


@router.get("/records/{entry_id}", response_model=schemas.ClinicalRecordEntryRead)
async def get_record_entry(
    entry_id: int,
    company_id: int = Depends(get_current_company_id),
    db: AsyncSession = Depends(get_db_with_tenant_context),
    actor: User = Depends(get_current_user),
) -> schemas.ClinicalRecordEntryRead:
    raw = await ClinicalRecordService.get_raw(db, company_id=company_id, entry_id=entry_id)
    await _require_clinical_read(
        db, actor=actor, patient_contact_id=raw.patient_contact_id,
        all_permission="medical:record:read-all", own_permission="medical:record:read-own-patients",
    )
    return await ClinicalRecordService.get(db, company_id=company_id, entry_id=entry_id, actor_user_id=actor.id)


@router.get("/patients/{patient_contact_id}/records", response_model=list[schemas.ClinicalRecordEntryRead])
async def list_record_entries(
    patient_contact_id: int,
    company_id: int = Depends(get_current_company_id),
    db: AsyncSession = Depends(get_db_with_tenant_context),
    actor: User = Depends(get_current_user),
) -> list[schemas.ClinicalRecordEntryRead]:
    await _require_clinical_read(
        db, actor=actor, patient_contact_id=patient_contact_id,
        all_permission="medical:record:read-all", own_permission="medical:record:read-own-patients",
    )
    return await ClinicalRecordService.list_for_patient(
        db, company_id=company_id, patient_contact_id=patient_contact_id, actor_user_id=actor.id
    )


# ---------------------------------------------------------------------------
# Agenda Médica
# ---------------------------------------------------------------------------
@router.post("/appointments", response_model=schemas.AppointmentRead, status_code=201)
async def create_appointment(
    payload: schemas.AppointmentCreate,
    company_id: int = Depends(get_current_company_id),
    db: AsyncSession = Depends(get_db_with_tenant_context),
    actor: User = Depends(require_permission("medical:appointment:create")),
) -> schemas.AppointmentRead:
    appointment = await AppointmentService.create(db, company_id=company_id, payload=payload, created_by=actor.id)
    return schemas.AppointmentRead.model_validate(appointment)


@router.get("/appointments", response_model=list[schemas.AppointmentRead])
async def list_appointments(
    professional_user_id: int | None = None,
    patient_contact_id: int | None = None,
    company_id: int = Depends(get_current_company_id),
    db: AsyncSession = Depends(get_db_with_tenant_context),
    _actor: User = Depends(require_permission("medical:appointment:list")),
) -> list[schemas.AppointmentRead]:
    appointments = await AppointmentService.list(
        db, company_id=company_id, professional_user_id=professional_user_id, patient_contact_id=patient_contact_id
    )
    return [schemas.AppointmentRead.model_validate(a) for a in appointments]


@router.get("/appointments/{appointment_id}", response_model=schemas.AppointmentRead)
async def get_appointment(
    appointment_id: int,
    company_id: int = Depends(get_current_company_id),
    db: AsyncSession = Depends(get_db_with_tenant_context),
    _actor: User = Depends(require_permission("medical:appointment:read")),
) -> schemas.AppointmentRead:
    appointment = await AppointmentService.get(db, company_id=company_id, appointment_id=appointment_id)
    return schemas.AppointmentRead.model_validate(appointment)


@router.post("/appointments/{appointment_id}/confirm", response_model=schemas.AppointmentRead)
async def confirm_appointment(
    appointment_id: int,
    company_id: int = Depends(get_current_company_id),
    db: AsyncSession = Depends(get_db_with_tenant_context),
    _actor: User = Depends(require_permission("medical:appointment:confirm")),
) -> schemas.AppointmentRead:
    appointment = await AppointmentService.confirm(db, company_id=company_id, appointment_id=appointment_id)
    return schemas.AppointmentRead.model_validate(appointment)


@router.post("/appointments/{appointment_id}/reschedule", response_model=schemas.AppointmentRead)
async def reschedule_appointment(
    appointment_id: int,
    payload: schemas.AppointmentReschedule,
    company_id: int = Depends(get_current_company_id),
    db: AsyncSession = Depends(get_db_with_tenant_context),
    _actor: User = Depends(require_permission("medical:appointment:reschedule")),
) -> schemas.AppointmentRead:
    appointment = await AppointmentService.reschedule(db, company_id=company_id, appointment_id=appointment_id, payload=payload)
    return schemas.AppointmentRead.model_validate(appointment)


@router.post("/appointments/{appointment_id}/cancel", response_model=schemas.AppointmentRead)
async def cancel_appointment(
    appointment_id: int,
    payload: schemas.AppointmentCancel,
    company_id: int = Depends(get_current_company_id),
    db: AsyncSession = Depends(get_db_with_tenant_context),
    _actor: User = Depends(require_permission("medical:appointment:cancel")),
) -> schemas.AppointmentRead:
    appointment = await AppointmentService.cancel(db, company_id=company_id, appointment_id=appointment_id, payload=payload)
    return schemas.AppointmentRead.model_validate(appointment)


@router.get("/appointments/{appointment_id}/consultation", response_model=schemas.ConsultationRead | None)
async def get_consultation_for_appointment(
    appointment_id: int,
    company_id: int = Depends(get_current_company_id),
    db: AsyncSession = Depends(get_db_with_tenant_context),
    actor: User = Depends(get_current_user),
) -> schemas.ConsultationRead | None:
    appointment = await AppointmentService.get(db, company_id=company_id, appointment_id=appointment_id)
    await _require_clinical_read(
        db, actor=actor, patient_contact_id=appointment.patient_contact_id,
        all_permission="medical:consultation:read-all", own_permission="medical:consultation:read-own-patients",
    )
    consultation = await get_by_appointment(
        db, company_id=company_id, appointment_id=appointment_id, actor_user_id=actor.id
    )
    return consultation


# ---------------------------------------------------------------------------
# Consulta
# ---------------------------------------------------------------------------
@router.post("/consultations", response_model=schemas.ConsultationRead, status_code=201)
async def create_consultation(
    payload: schemas.ConsultationCreate,
    company_id: int = Depends(get_current_company_id),
    db: AsyncSession = Depends(get_db_with_tenant_context),
    actor: User = Depends(require_permission("medical:consultation:create")),
) -> schemas.ConsultationRead:
    return await ConsultationService.create(db, company_id=company_id, payload=payload, created_by=actor.id)


@router.post("/consultations/{consultation_id}/correct", response_model=schemas.ConsultationRead)
async def correct_consultation(
    consultation_id: int,
    payload: schemas.ConsultationCorrect,
    company_id: int = Depends(get_current_company_id),
    db: AsyncSession = Depends(get_db_with_tenant_context),
    actor: User = Depends(require_permission("medical:consultation:create")),
) -> schemas.ConsultationRead:
    return await ConsultationService.correct(
        db, company_id=company_id, consultation_id=consultation_id, payload=payload, created_by=actor.id
    )


@router.get("/consultations/{consultation_id}", response_model=schemas.ConsultationRead)
async def get_consultation(
    consultation_id: int,
    company_id: int = Depends(get_current_company_id),
    db: AsyncSession = Depends(get_db_with_tenant_context),
    actor: User = Depends(get_current_user),
) -> schemas.ConsultationRead:
    # Chequeo de patient_contact_id antes de descifrar (misma estrategia
    # que get_record_entry): una consulta a la tabla sin las columnas
    # cifradas alcanza para saber a qué paciente pertenece.
    raw = (
        await db.execute(
            select(medical_models.Consultation.patient_contact_id).where(
                medical_models.Consultation.company_id == company_id, medical_models.Consultation.id == consultation_id
            )
        )
    ).scalar_one_or_none()
    if raw is None:
        raise NotFoundError(f"Consulta {consultation_id} no encontrada")

    await _require_clinical_read(
        db, actor=actor, patient_contact_id=raw,
        all_permission="medical:consultation:read-all", own_permission="medical:consultation:read-own-patients",
    )
    return await ConsultationService.get(db, company_id=company_id, consultation_id=consultation_id, actor_user_id=actor.id)


# ---------------------------------------------------------------------------
# Módulo 10 — Recetas
# ---------------------------------------------------------------------------
@router.post("/prescriptions", response_model=schemas.PrescriptionRead, status_code=201)
async def create_prescription(
    payload: schemas.PrescriptionCreate,
    company_id: int = Depends(get_current_company_id),
    db: AsyncSession = Depends(get_db_with_tenant_context),
    actor: User = Depends(require_permission("medical:prescription:create")),
) -> schemas.PrescriptionRead:
    return await PrescriptionService.create(db, company_id=company_id, payload=payload, created_by=actor.id)


@router.get("/prescriptions/{prescription_id}", response_model=schemas.PrescriptionRead)
async def get_prescription(
    prescription_id: int,
    company_id: int = Depends(get_current_company_id),
    db: AsyncSession = Depends(get_db_with_tenant_context),
    actor: User = Depends(get_current_user),
) -> schemas.PrescriptionRead:
    raw = (
        await db.execute(
            select(medical_models.Prescription.patient_contact_id).where(
                medical_models.Prescription.company_id == company_id, medical_models.Prescription.id == prescription_id
            )
        )
    ).scalar_one_or_none()
    if raw is None:
        raise NotFoundError(f"Receta {prescription_id} no encontrada")

    await _require_clinical_read(
        db, actor=actor, patient_contact_id=raw,
        all_permission="medical:prescription:read-all", own_permission="medical:prescription:read-own-patients",
    )
    return await PrescriptionService.get(db, company_id=company_id, prescription_id=prescription_id, actor_user_id=actor.id)


@router.get("/patients/{patient_contact_id}/prescriptions", response_model=list[schemas.PrescriptionRead])
async def list_prescriptions_for_patient(
    patient_contact_id: int,
    company_id: int = Depends(get_current_company_id),
    db: AsyncSession = Depends(get_db_with_tenant_context),
    actor: User = Depends(get_current_user),
) -> list[schemas.PrescriptionRead]:
    await _require_clinical_read(
        db, actor=actor, patient_contact_id=patient_contact_id,
        all_permission="medical:prescription:read-all", own_permission="medical:prescription:read-own-patients",
    )
    return await PrescriptionService.list_for_patient(db, company_id=company_id, patient_contact_id=patient_contact_id, actor_user_id=actor.id)


@router.post("/prescriptions/{prescription_id}/void", response_model=schemas.PrescriptionRead)
async def void_prescription(
    prescription_id: int,
    payload: schemas.PrescriptionVoid,
    company_id: int = Depends(get_current_company_id),
    db: AsyncSession = Depends(get_db_with_tenant_context),
    actor: User = Depends(require_permission("medical:prescription:create")),
) -> schemas.PrescriptionRead:
    return await PrescriptionService.void(db, company_id=company_id, prescription_id=prescription_id, payload=payload, actor_user_id=actor.id)


# ---------------------------------------------------------------------------
# Módulo 11 — Laboratorio
# ---------------------------------------------------------------------------
@router.post("/lab-orders", response_model=schemas.LabOrderRead, status_code=201)
async def create_lab_order(
    payload: schemas.LabOrderCreate,
    company_id: int = Depends(get_current_company_id),
    db: AsyncSession = Depends(get_db_with_tenant_context),
    actor: User = Depends(require_permission("medical:lab_order:create")),
) -> schemas.LabOrderRead:
    return await LabOrderService.create(db, company_id=company_id, payload=payload, created_by=actor.id)


@router.get("/lab-orders/{lab_order_id}", response_model=schemas.LabOrderRead)
async def get_lab_order(
    lab_order_id: int,
    company_id: int = Depends(get_current_company_id),
    db: AsyncSession = Depends(get_db_with_tenant_context),
    actor: User = Depends(get_current_user),
) -> schemas.LabOrderRead:
    raw = (
        await db.execute(
            select(medical_models.LabOrder.patient_contact_id).where(
                medical_models.LabOrder.company_id == company_id, medical_models.LabOrder.id == lab_order_id
            )
        )
    ).scalar_one_or_none()
    if raw is None:
        raise NotFoundError(f"Orden de laboratorio {lab_order_id} no encontrada")
    await _require_clinical_read(
        db, actor=actor, patient_contact_id=raw,
        all_permission="medical:lab_order:read-all", own_permission="medical:lab_order:read-own-patients",
    )
    return await LabOrderService.get(db, company_id=company_id, lab_order_id=lab_order_id, actor_user_id=actor.id)


@router.get("/patients/{patient_contact_id}/lab-orders", response_model=list[schemas.LabOrderRead])
async def list_lab_orders_for_patient(
    patient_contact_id: int,
    company_id: int = Depends(get_current_company_id),
    db: AsyncSession = Depends(get_db_with_tenant_context),
    actor: User = Depends(get_current_user),
) -> list[schemas.LabOrderRead]:
    await _require_clinical_read(
        db, actor=actor, patient_contact_id=patient_contact_id,
        all_permission="medical:lab_order:read-all", own_permission="medical:lab_order:read-own-patients",
    )
    return await LabOrderService.list_for_patient(db, company_id=company_id, patient_contact_id=patient_contact_id, actor_user_id=actor.id)


@router.post("/lab-order-tests/{lab_order_test_id}/result", response_model=schemas.LabOrderTestRead)
async def enter_lab_order_test_result(
    lab_order_test_id: int,
    payload: schemas.LabOrderTestResult,
    company_id: int = Depends(get_current_company_id),
    db: AsyncSession = Depends(get_db_with_tenant_context),
    actor: User = Depends(require_permission("medical:lab_order:create")),
) -> schemas.LabOrderTestRead:
    test = await LabOrderService.enter_result(
        db, company_id=company_id, lab_order_test_id=lab_order_test_id, payload=payload, actor_user_id=actor.id
    )
    return schemas.LabOrderTestRead.model_validate(test)


@router.post("/lab-order-tests/{lab_order_test_id}/attachments", response_model=schemas.AttachmentRead, status_code=201)
async def upload_lab_order_test_attachment(
    lab_order_test_id: int,
    file: UploadFile = File(...),
    company_id: int = Depends(get_current_company_id),
    db: AsyncSession = Depends(get_db_with_tenant_context),
    actor: User = Depends(require_permission("medical:lab_order:create")),
) -> schemas.AttachmentRead:
    content = await file.read()
    attachment = await LabOrderService.add_attachment(
        db, company_id=company_id, lab_order_test_id=lab_order_test_id,
        filename=file.filename or "adjunto", mime_type=file.content_type or "application/octet-stream",
        content=content, uploaded_by=actor.id,
    )
    return schemas.AttachmentRead.model_validate(attachment)


@router.get("/lab-order-tests/{lab_order_test_id}/attachments", response_model=list[schemas.AttachmentRead])
async def list_lab_order_test_attachments(
    lab_order_test_id: int,
    company_id: int = Depends(get_current_company_id),
    db: AsyncSession = Depends(get_db_with_tenant_context),
    _actor: User = Depends(get_current_user),
) -> list[schemas.AttachmentRead]:
    attachments = await LabOrderService.list_attachments(db, company_id=company_id, lab_order_test_id=lab_order_test_id)
    return [schemas.AttachmentRead.model_validate(a) for a in attachments]


@router.get("/attachments/{attachment_id}/download")
async def download_attachment(
    attachment_id: int,
    company_id: int = Depends(get_current_company_id),
    db: AsyncSession = Depends(get_db_with_tenant_context),
    _actor: User = Depends(get_current_user),
) -> Response:
    attachment = await AttachmentService.get(db, company_id=company_id, attachment_id=attachment_id)
    if attachment is None:
        raise NotFoundError(f"Adjunto {attachment_id} no encontrado")
    content = AttachmentService.read_bytes(attachment)
    return Response(
        content=content, media_type=attachment.mime_type,
        headers={"Content-Disposition": f'attachment; filename="{attachment.filename}"'},
    )


# ---------------------------------------------------------------------------------
# Módulo 12 — Teleconsulta
# ---------------------------------------------------------------------------------------------
@router.post("/teleconsultations", response_model=schemas.TeleconsultationSessionRead, status_code=201)
async def create_teleconsultation(
    payload: schemas.TeleconsultationSessionCreate,
    company_id: int = Depends(get_current_company_id),
    db: AsyncSession = Depends(get_db_with_tenant_context),
    actor: User = Depends(require_permission("medical:teleconsultation:create")),
) -> schemas.TeleconsultationSessionRead:
    session = await TeleconsultationService.create(db, company_id=company_id, payload=payload, created_by=actor.id)
    return schemas.TeleconsultationSessionRead.model_validate(session)


@router.get("/teleconsultations/{session_id}", response_model=schemas.TeleconsultationSessionRead)
async def get_teleconsultation(
    session_id: int,
    company_id: int = Depends(get_current_company_id),
    db: AsyncSession = Depends(get_db_with_tenant_context),
    actor: User = Depends(get_current_user),
) -> schemas.TeleconsultationSessionRead:
    session = await TeleconsultationService.get(db, company_id=company_id, session_id=session_id)
    await _require_clinical_read(
        db, actor=actor, patient_contact_id=session.patient_contact_id,
        all_permission="medical:teleconsultation:read-all", own_permission="medical:teleconsultation:read-own-patients",
    )
    return schemas.TeleconsultationSessionRead.model_validate(session)


@router.get("/appointments/{appointment_id}/teleconsultation", response_model=schemas.TeleconsultationSessionRead | None)
async def get_teleconsultation_for_appointment(
    appointment_id: int,
    company_id: int = Depends(get_current_company_id),
    db: AsyncSession = Depends(get_db_with_tenant_context),
    actor: User = Depends(get_current_user),
) -> schemas.TeleconsultationSessionRead | None:
    appointment = await AppointmentService.get(db, company_id=company_id, appointment_id=appointment_id)
    await _require_clinical_read(
        db, actor=actor, patient_contact_id=appointment.patient_contact_id,
        all_permission="medical:teleconsultation:read-all", own_permission="medical:teleconsultation:read-own-patients",
    )
    session = await TeleconsultationService.get_by_appointment(db, company_id=company_id, appointment_id=appointment_id)
    return schemas.TeleconsultationSessionRead.model_validate(session) if session else None


@router.post("/teleconsultations/{session_id}/start", response_model=schemas.TeleconsultationSessionRead)
async def start_teleconsultation(
    session_id: int,
    company_id: int = Depends(get_current_company_id),
    db: AsyncSession = Depends(get_db_with_tenant_context),
    _actor: User = Depends(require_permission("medical:teleconsultation:create")),
) -> schemas.TeleconsultationSessionRead:
    session = await TeleconsultationService.start(db, company_id=company_id, session_id=session_id)
    return schemas.TeleconsultationSessionRead.model_validate(session)


@router.post("/teleconsultations/{session_id}/end", response_model=schemas.TeleconsultationSessionRead)
async def end_teleconsultation(
    session_id: int,
    company_id: int = Depends(get_current_company_id),
    db: AsyncSession = Depends(get_db_with_tenant_context),
    _actor: User = Depends(require_permission("medical:teleconsultation:create")),
) -> schemas.TeleconsultationSessionRead:
    session = await TeleconsultationService.end(db, company_id=company_id, session_id=session_id)
    return schemas.TeleconsultationSessionRead.model_validate(session)


# ---------------------------------------------------------------------------------
# Módulo 13 — Facturación Médica Básica
# ---------------------------------------------------------------------------
@router.post("/billing", response_model=schemas.MedicalBillingRecordRead, status_code=201)
async def create_medical_billing(
    payload: schemas.MedicalBillingCreate,
    company_id: int = Depends(get_current_company_id),
    db: AsyncSession = Depends(get_db_with_tenant_context),
    actor: User = Depends(require_permission("medical:billing:create")),
) -> schemas.MedicalBillingRecordRead:
    record = await MedicalBillingService.create(db, company_id=company_id, payload=payload, created_by=actor.id)
    return schemas.MedicalBillingRecordRead.model_validate(record)


@router.get("/consultations/{consultation_id}/billing", response_model=schemas.MedicalBillingRecordRead | None)
async def get_medical_billing_for_consultation(
    consultation_id: int,
    company_id: int = Depends(get_current_company_id),
    db: AsyncSession = Depends(get_db_with_tenant_context),
    actor: User = Depends(get_current_user),
) -> schemas.MedicalBillingRecordRead | None:
    consultation = await ConsultationService.get(
        db, company_id=company_id, consultation_id=consultation_id, actor_user_id=actor.id
    )
    await _require_clinical_read(
        db, actor=actor, patient_contact_id=consultation.patient_contact_id,
        all_permission="medical:billing:read-all", own_permission="medical:billing:read-own-patients",
    )
    record = await MedicalBillingService.get_for_consultation(db, company_id=company_id, consultation_id=consultation_id)
    return schemas.MedicalBillingRecordRead.model_validate(record) if record else None


@router.post("/billing/{record_id}/cancel", response_model=schemas.MedicalBillingRecordRead)
async def cancel_medical_billing(
    record_id: int,
    payload: schemas.MedicalBillingCancel,
    company_id: int = Depends(get_current_company_id),
    db: AsyncSession = Depends(get_db_with_tenant_context),
    actor: User = Depends(require_permission("medical:billing:create")),
) -> schemas.MedicalBillingRecordRead:
    record = await MedicalBillingService.cancel(db, company_id=company_id, record_id=record_id, payload=payload, actor_id=actor.id)
    return schemas.MedicalBillingRecordRead.model_validate(record)


# ---------------------------------------------------------------------------------
# Módulo 14 — Portal / Mensajería Paciente-Médico
# ---------------------------------------------------------------------------
@router.post("/messages", response_model=schemas.PatientMessageRead, status_code=201)
async def send_patient_message(
    payload: schemas.PatientMessageCreate,
    company_id: int = Depends(get_current_company_id),
    db: AsyncSession = Depends(get_db_with_tenant_context),
    actor: User = Depends(require_permission("medical:message:create")),
) -> schemas.PatientMessageRead:
    message = await PatientMessageService.send(db, company_id=company_id, payload=payload, author_user_id=actor.id)
    return schemas.PatientMessageRead.model_validate(message)


@router.get("/patients/{patient_contact_id}/messages", response_model=list[schemas.PatientMessageRead])
async def list_patient_messages(
    patient_contact_id: int,
    company_id: int = Depends(get_current_company_id),
    db: AsyncSession = Depends(get_db_with_tenant_context),
    actor: User = Depends(get_current_user),
) -> list[schemas.PatientMessageRead]:
    await _require_clinical_read(
        db, actor=actor, patient_contact_id=patient_contact_id,
        all_permission="medical:message:read-all", own_permission="medical:message:read-own-patients",
    )
    messages = await PatientMessageService.list_for_patient(db, company_id=company_id, patient_contact_id=patient_contact_id)
    return [schemas.PatientMessageRead.model_validate(m) for m in messages]


@router.post("/messages/{message_id}/read", response_model=schemas.PatientMessageRead)
async def mark_patient_message_read(
    message_id: int,
    company_id: int = Depends(get_current_company_id),
    db: AsyncSession = Depends(get_db_with_tenant_context),
    _actor: User = Depends(require_permission("medical:message:create")),
) -> schemas.PatientMessageRead:
    message = await PatientMessageService.mark_read(db, company_id=company_id, message_id=message_id)
    return schemas.PatientMessageRead.model_validate(message)


# ---------------------------------------------------------------------------
# Módulo 15 — Reserva Pública de Citas (widget embebible, sin JWT)
# ---------------------------------------------------------------------------
public_router = APIRouter(prefix="/public/medical", tags=["medical-public"])


@public_router.get("/{company_id}/professionals/{professional_user_id}/busy-slots", response_model=list[schemas.PublicBusySlot])
async def get_public_busy_slots(
    company_id: int,
    professional_user_id: int,
    date_from: datetime,
    date_to: datetime,
    db: AsyncSession = Depends(get_public_db_context),
) -> list[schemas.PublicBusySlot]:
    await ensure_public_booking_active(db, company_id=company_id)
    slots = await PublicBookingService.list_busy_slots(
        db, company_id=company_id, professional_user_id=professional_user_id, date_from=date_from, date_to=date_to,
    )
    return [schemas.PublicBusySlot.model_validate(s) for s in slots]


@public_router.post("/{company_id}/bookings", response_model=schemas.PublicBookingRead, status_code=201)
async def create_public_booking(
    company_id: int,
    payload: schemas.PublicBookingCreate,
    db: AsyncSession = Depends(get_public_db_context),
) -> schemas.PublicBookingRead:
    await ensure_public_booking_active(db, company_id=company_id)
    appointment = await PublicBookingService.create(db, company_id=company_id, payload=payload)
    return schemas.PublicBookingRead(
        appointment_id=appointment.id,
        scheduled_start=appointment.scheduled_start,
        scheduled_end=appointment.scheduled_end,
        status=appointment.status,
    )
