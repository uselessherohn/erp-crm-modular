"""
Routers de pharmacy. Todas las rutas exigen el paquete `pharmacy` activo.
Sin RBAC "own patients"/"read-all" (a diferencia de `medical`) — la spec
8.3 no exige ese patrón para Farmacéutico como sí lo hace 8.2 para
Médico; permisos planos, mismo estilo que `sales`/`purchasing`.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_company_id, get_db_with_tenant_context, require_package, require_permission
from app.core.models import User
from app.pharmacy import schemas
from app.purchasing import schemas as purchasing_schemas
from app.pharmacy.services import (
    ControlledSubstanceLogService,
    ControlledSubstanceService,
    DispensationService,
    DrugInteractionService,
    InsuranceClaimService,
    InsuranceProviderService,
    MtmSessionService,
    PatientInsurancePolicyService,
    ProductActiveIngredientService,
    ReorderPointService,
    ReorderSuggestionService,
)

router = APIRouter(prefix="/pharmacy", tags=["pharmacy"], dependencies=[Depends(require_package("pharmacy"))])


# ---------------------------------------------------------------------------------
# Dispensación / POS Farmacia
# ---------------------------------------------------------------------------
@router.post("/dispensations", response_model=schemas.DispensationOrderRead, status_code=201)
async def create_dispensation(
    payload: schemas.DispensationOrderCreate,
    company_id: int = Depends(get_current_company_id),
    db: AsyncSession = Depends(get_db_with_tenant_context),
    actor: User = Depends(require_permission("pharmacy:dispensation:create")),
) -> schemas.DispensationOrderRead:
    return await DispensationService.create(db, company_id=company_id, payload=payload, dispensed_by=actor.id)


@router.get("/dispensations/{order_id}", response_model=schemas.DispensationOrderRead)
async def get_dispensation(
    order_id: int,
    company_id: int = Depends(get_current_company_id),
    db: AsyncSession = Depends(get_db_with_tenant_context),
    _actor: User = Depends(require_permission("pharmacy:dispensation:read")),
) -> schemas.DispensationOrderRead:
    return await DispensationService.get(db, company_id=company_id, order_id=order_id)


@router.get("/patients/{patient_contact_id}/dispensations", response_model=list[schemas.DispensationOrderRead])
async def list_dispensations_for_patient(
    patient_contact_id: int,
    company_id: int = Depends(get_current_company_id),
    db: AsyncSession = Depends(get_db_with_tenant_context),
    _actor: User = Depends(require_permission("pharmacy:dispensation:read")),
) -> list[schemas.DispensationOrderRead]:
    return await DispensationService.list_for_patient(db, company_id=company_id, patient_contact_id=patient_contact_id)


@router.post("/dispensations/{order_id}/void", response_model=schemas.DispensationOrderRead)
async def void_dispensation(
    order_id: int,
    payload: schemas.DispensationVoid,
    company_id: int = Depends(get_current_company_id),
    db: AsyncSession = Depends(get_db_with_tenant_context),
    actor: User = Depends(require_permission("pharmacy:dispensation:create")),
) -> schemas.DispensationOrderRead:
    return await DispensationService.void(db, company_id=company_id, order_id=order_id, payload=payload, actor_id=actor.id)


# ---------------------------------------------------------------------------------
# Sustancias Controladas
# ---------------------------------------------------------------------------
@router.post("/controlled-substances", response_model=schemas.ControlledSubstanceProductRead, status_code=201)
async def mark_controlled_substance(
    payload: schemas.ControlledSubstanceMark,
    company_id: int = Depends(get_current_company_id),
    db: AsyncSession = Depends(get_db_with_tenant_context),
    actor: User = Depends(require_permission("pharmacy:controlled_substance:manage")),
) -> schemas.ControlledSubstanceProductRead:
    row = await ControlledSubstanceService.mark(db, company_id=company_id, product_id=payload.product_id, created_by=actor.id)
    return schemas.ControlledSubstanceProductRead.model_validate(row)


@router.delete("/controlled-substances/{product_id}", status_code=204)
async def unmark_controlled_substance(
    product_id: int,
    company_id: int = Depends(get_current_company_id),
    db: AsyncSession = Depends(get_db_with_tenant_context),
    _actor: User = Depends(require_permission("pharmacy:controlled_substance:manage")),
) -> None:
    await ControlledSubstanceService.unmark(db, company_id=company_id, product_id=product_id)


@router.get("/controlled-substances", response_model=list[schemas.ControlledSubstanceProductRead])
async def list_controlled_substances(
    company_id: int = Depends(get_current_company_id),
    db: AsyncSession = Depends(get_db_with_tenant_context),
    _actor: User = Depends(require_permission("pharmacy:controlled_substance:manage")),
) -> list[schemas.ControlledSubstanceProductRead]:
    rows = await ControlledSubstanceService.list(db, company_id=company_id)
    return [schemas.ControlledSubstanceProductRead.model_validate(r) for r in rows]



# ---------------------------------------------------------------------------
# Módulo 21 — MTM / Consulta Farmacéutica
# ---------------------------------------------------------------------------
@router.post("/mtm-sessions", response_model=schemas.MtmSessionRead, status_code=201)
async def create_mtm_session(
    payload: schemas.MtmSessionCreate,
    company_id: int = Depends(get_current_company_id),
    db: AsyncSession = Depends(get_db_with_tenant_context),
    actor: User = Depends(require_permission("pharmacy:mtm_session:create")),
) -> schemas.MtmSessionRead:
    session = await MtmSessionService.create(db, company_id=company_id, payload=payload, pharmacist_user_id=actor.id)
    return schemas.MtmSessionRead.model_validate(session)


@router.get("/patients/{patient_contact_id}/mtm-sessions", response_model=list[schemas.MtmSessionRead])
async def list_mtm_sessions_for_patient(
    patient_contact_id: int,
    company_id: int = Depends(get_current_company_id),
    db: AsyncSession = Depends(get_db_with_tenant_context),
    _actor: User = Depends(require_permission("pharmacy:mtm_session:read")),
) -> list[schemas.MtmSessionRead]:
    rows = await MtmSessionService.list_for_patient(db, company_id=company_id, patient_contact_id=patient_contact_id)
    return [schemas.MtmSessionRead.model_validate(r) for r in rows]


@router.get("/mtm-sessions/{session_id}", response_model=schemas.MtmSessionRead)
async def get_mtm_session(
    session_id: int,
    company_id: int = Depends(get_current_company_id),
    db: AsyncSession = Depends(get_db_with_tenant_context),
    _actor: User = Depends(require_permission("pharmacy:mtm_session:read")),
) -> schemas.MtmSessionRead:
    session = await MtmSessionService.get(db, company_id=company_id, session_id=session_id)
    return schemas.MtmSessionRead.model_validate(session)


@router.post("/mtm-sessions/{session_id}/cancel", response_model=schemas.MtmSessionRead)
async def cancel_mtm_session(
    session_id: int,
    payload: schemas.MtmSessionCancel,
    company_id: int = Depends(get_current_company_id),
    db: AsyncSession = Depends(get_db_with_tenant_context),
    actor: User = Depends(require_permission("pharmacy:mtm_session:create")),
) -> schemas.MtmSessionRead:
    session = await MtmSessionService.cancel(db, company_id=company_id, session_id=session_id, payload=payload, actor_id=actor.id)
    return schemas.MtmSessionRead.model_validate(session)


@router.post("/mtm-sessions/{session_id}/close", response_model=schemas.MtmBillingRecordRead)
async def close_mtm_session(
    session_id: int,
    payload: schemas.MtmSessionClose,
    company_id: int = Depends(get_current_company_id),
    db: AsyncSession = Depends(get_db_with_tenant_context),
    actor: User = Depends(require_permission("pharmacy:mtm_session:create")),
) -> schemas.MtmBillingRecordRead:
    billing_record = await MtmSessionService.close(db, company_id=company_id, session_id=session_id, payload=payload, actor_id=actor.id)
    return schemas.MtmBillingRecordRead.model_validate(billing_record)


@router.get("/mtm-sessions/{session_id}/billing", response_model=schemas.MtmBillingRecordRead | None)
async def get_mtm_session_billing(
    session_id: int,
    company_id: int = Depends(get_current_company_id),
    db: AsyncSession = Depends(get_db_with_tenant_context),
    _actor: User = Depends(require_permission("pharmacy:mtm_session:read")),
) -> schemas.MtmBillingRecordRead | None:
    record = await MtmSessionService.get_billing_for_session(db, company_id=company_id, session_id=session_id)
    return schemas.MtmBillingRecordRead.model_validate(record) if record is not None else None


@router.post("/mtm-billing-records/{billing_record_id}/cancel", response_model=schemas.MtmBillingRecordRead)
async def cancel_mtm_billing_record(
    billing_record_id: int,
    payload: schemas.MtmSessionCancel,
    company_id: int = Depends(get_current_company_id),
    db: AsyncSession = Depends(get_db_with_tenant_context),
    actor: User = Depends(require_permission("pharmacy:mtm_session:create")),
) -> schemas.MtmBillingRecordRead:
    record = await MtmSessionService.cancel_billing(
        db, company_id=company_id, billing_record_id=billing_record_id, payload=payload, actor_id=actor.id
    )
    return schemas.MtmBillingRecordRead.model_validate(record)


# ---------------------------------------------------------------------------
# Módulo 20 — Reposición a Droguerías
# ---------------------------------------------------------------------------
@router.put("/reorder-points", response_model=schemas.ReorderPointRead)
async def upsert_reorder_point(
    payload: schemas.ReorderPointUpsert,
    company_id: int = Depends(get_current_company_id),
    db: AsyncSession = Depends(get_db_with_tenant_context),
    actor: User = Depends(require_permission("pharmacy:reorder_point:manage")),
) -> schemas.ReorderPointRead:
    point = await ReorderPointService.upsert(db, company_id=company_id, payload=payload, actor_id=actor.id)
    return schemas.ReorderPointRead.model_validate(point)


@router.get("/reorder-points", response_model=list[schemas.ReorderPointRead])
async def list_reorder_points(
    warehouse_id: int | None = Query(None),
    company_id: int = Depends(get_current_company_id),
    db: AsyncSession = Depends(get_db_with_tenant_context),
    _actor: User = Depends(require_permission("pharmacy:reorder_point:read")),
) -> list[schemas.ReorderPointRead]:
    points = await ReorderPointService.list(db, company_id=company_id, warehouse_id=warehouse_id)
    return [schemas.ReorderPointRead.model_validate(p) for p in points]


@router.delete("/reorder-points/{reorder_point_id}", status_code=204)
async def delete_reorder_point(
    reorder_point_id: int,
    company_id: int = Depends(get_current_company_id),
    db: AsyncSession = Depends(get_db_with_tenant_context),
    _actor: User = Depends(require_permission("pharmacy:reorder_point:manage")),
) -> None:
    await ReorderPointService.delete(db, company_id=company_id, reorder_point_id=reorder_point_id)


@router.get("/reorder-suggestions", response_model=list[schemas.ReorderSuggestionRead])
async def list_reorder_suggestions(
    warehouse_id: int = Query(...),
    company_id: int = Depends(get_current_company_id),
    db: AsyncSession = Depends(get_db_with_tenant_context),
    _actor: User = Depends(require_permission("pharmacy:reorder_point:read")),
) -> list[schemas.ReorderSuggestionRead]:
    return await ReorderSuggestionService.list_suggestions(db, company_id=company_id, warehouse_id=warehouse_id)


@router.post("/reorder-suggestions/generate-purchase-order", response_model=purchasing_schemas.PurchaseOrderRead, status_code=201)
async def generate_purchase_order_from_suggestions(
    payload: schemas.ReorderPurchaseOrderGenerate,
    company_id: int = Depends(get_current_company_id),
    db: AsyncSession = Depends(get_db_with_tenant_context),
    actor: User = Depends(require_permission("pharmacy:reorder_point:manage")),
) -> purchasing_schemas.PurchaseOrderRead:
    po = await ReorderSuggestionService.generate_purchase_order(db, company_id=company_id, payload=payload, actor_id=actor.id)
    return purchasing_schemas.PurchaseOrderRead.model_validate(po)

@router.get("/controlled-substances/log", response_model=list[schemas.ControlledSubstanceLogEntryRead])
async def list_controlled_substance_log(
    company_id: int = Depends(get_current_company_id),
    db: AsyncSession = Depends(get_db_with_tenant_context),
    _actor: User = Depends(require_permission("pharmacy:controlled_substance:read-log")),
) -> list[schemas.ControlledSubstanceLogEntryRead]:
    rows = await ControlledSubstanceLogService.list(db, company_id=company_id)
    return [schemas.ControlledSubstanceLogEntryRead.model_validate(r) for r in rows]


# ---------------------------------------------------------------------------------
# Interacciones [extendido] — módulo 17. Ver DED-58 a DED-61 en models.py.
# ---------------------------------------------------------------------------
@router.put("/products/{product_id}/active-ingredient", response_model=schemas.ProductActiveIngredientRead)
async def set_product_active_ingredient(
    product_id: int,
    payload: schemas.ProductActiveIngredientSet,
    company_id: int = Depends(get_current_company_id),
    db: AsyncSession = Depends(get_db_with_tenant_context),
    actor: User = Depends(require_permission("pharmacy:interaction:manage")),
) -> schemas.ProductActiveIngredientRead:
    if payload.product_id != product_id:
        payload = schemas.ProductActiveIngredientSet(product_id=product_id, active_ingredient=payload.active_ingredient)
    row = await ProductActiveIngredientService.set(db, company_id=company_id, payload=payload, created_by=actor.id)
    return schemas.ProductActiveIngredientRead.model_validate(row)


@router.get("/products/active-ingredients", response_model=list[schemas.ProductActiveIngredientRead])
async def list_product_active_ingredients(
    company_id: int = Depends(get_current_company_id),
    db: AsyncSession = Depends(get_db_with_tenant_context),
    _actor: User = Depends(require_permission("pharmacy:interaction:manage")),
) -> list[schemas.ProductActiveIngredientRead]:
    rows = await ProductActiveIngredientService.list(db, company_id=company_id)
    return [schemas.ProductActiveIngredientRead.model_validate(r) for r in rows]


@router.post("/interactions/check", response_model=schemas.InteractionCheckResult)
async def check_interactions(
    payload: schemas.InteractionCheckRequest,
    company_id: int = Depends(get_current_company_id),
    db: AsyncSession = Depends(get_db_with_tenant_context),
    _actor: User = Depends(require_permission("pharmacy:interaction:check")),
) -> schemas.InteractionCheckResult:
    return await DrugInteractionService.check(db, company_id=company_id, payload=payload)


# ---------------------------------------------------------------------------------------------
# Módulo 18 — Aseguradoras [extendido]. Ver DED-62 a DED-64 en models.py.
# ---------------------------------------------------------------------------------------------
@router.post("/insurance-providers", response_model=schemas.InsuranceProviderRead, status_code=201)
async def create_insurance_provider(
    payload: schemas.InsuranceProviderCreate,
    company_id: int = Depends(get_current_company_id),
    db: AsyncSession = Depends(get_db_with_tenant_context),
    _actor: User = Depends(require_permission("pharmacy:insurance:manage")),
) -> schemas.InsuranceProviderRead:
    provider = await InsuranceProviderService.create(db, company_id=company_id, payload=payload)
    return schemas.InsuranceProviderRead.model_validate(provider)


@router.get("/insurance-providers", response_model=list[schemas.InsuranceProviderRead])
async def list_insurance_providers(
    company_id: int = Depends(get_current_company_id),
    db: AsyncSession = Depends(get_db_with_tenant_context),
    _actor: User = Depends(require_permission("pharmacy:insurance:manage")),
) -> list[schemas.InsuranceProviderRead]:
    rows = await InsuranceProviderService.list(db, company_id=company_id)
    return [schemas.InsuranceProviderRead.model_validate(r) for r in rows]


@router.post("/insurance-policies", response_model=schemas.PatientInsurancePolicyRead, status_code=201)
async def create_patient_insurance_policy(
    payload: schemas.PatientInsurancePolicyCreate,
    company_id: int = Depends(get_current_company_id),
    db: AsyncSession = Depends(get_db_with_tenant_context),
    _actor: User = Depends(require_permission("pharmacy:insurance:manage")),
) -> schemas.PatientInsurancePolicyRead:
    policy = await PatientInsurancePolicyService.create(db, company_id=company_id, payload=payload)
    return schemas.PatientInsurancePolicyRead.model_validate(policy)


@router.get("/insurance-policies/patient/{patient_contact_id}", response_model=list[schemas.PatientInsurancePolicyRead])
async def list_patient_insurance_policies(
    patient_contact_id: int,
    company_id: int = Depends(get_current_company_id),
    db: AsyncSession = Depends(get_db_with_tenant_context),
    _actor: User = Depends(require_permission("pharmacy:insurance:manage")),
) -> list[schemas.PatientInsurancePolicyRead]:
    rows = await PatientInsurancePolicyService.list_for_patient(db, company_id=company_id, patient_contact_id=patient_contact_id)
    return [schemas.PatientInsurancePolicyRead.model_validate(r) for r in rows]


@router.post("/insurance-claims", response_model=schemas.InsuranceClaimRead, status_code=201)
async def create_insurance_claim(
    payload: schemas.InsuranceClaimCreate,
    company_id: int = Depends(get_current_company_id),
    db: AsyncSession = Depends(get_db_with_tenant_context),
    _actor: User = Depends(require_permission("pharmacy:insurance:claim")),
) -> schemas.InsuranceClaimRead:
    claim = await InsuranceClaimService.create(db, company_id=company_id, payload=payload)
    return schemas.InsuranceClaimRead.model_validate(claim)


@router.get("/insurance-claims", response_model=list[schemas.InsuranceClaimRead])
async def list_insurance_claims(
    company_id: int = Depends(get_current_company_id),
    db: AsyncSession = Depends(get_db_with_tenant_context),
    _actor: User = Depends(require_permission("pharmacy:insurance:claim")),
) -> list[schemas.InsuranceClaimRead]:
    rows = await InsuranceClaimService.list(db, company_id=company_id)
    return [schemas.InsuranceClaimRead.model_validate(r) for r in rows]


@router.get("/insurance-claims/{claim_id}", response_model=schemas.InsuranceClaimRead)
async def get_insurance_claim(
    claim_id: int,
    company_id: int = Depends(get_current_company_id),
    db: AsyncSession = Depends(get_db_with_tenant_context),
    _actor: User = Depends(require_permission("pharmacy:insurance:claim")),
) -> schemas.InsuranceClaimRead:
    claim = await InsuranceClaimService.get(db, company_id=company_id, claim_id=claim_id)
    return schemas.InsuranceClaimRead.model_validate(claim)


@router.post("/insurance-claims/{claim_id}/submit", response_model=schemas.InsuranceClaimRead)
async def submit_insurance_claim(
    claim_id: int,
    company_id: int = Depends(get_current_company_id),
    db: AsyncSession = Depends(get_db_with_tenant_context),
    _actor: User = Depends(require_permission("pharmacy:insurance:claim")),
) -> schemas.InsuranceClaimRead:
    claim = await InsuranceClaimService.submit(db, company_id=company_id, claim_id=claim_id)
    return schemas.InsuranceClaimRead.model_validate(claim)


@router.post("/insurance-claims/{claim_id}/reject", response_model=schemas.InsuranceClaimRead)
async def reject_insurance_claim(
    claim_id: int,
    payload: schemas.InsuranceClaimReject,
    company_id: int = Depends(get_current_company_id),
    db: AsyncSession = Depends(get_db_with_tenant_context),
    _actor: User = Depends(require_permission("pharmacy:insurance:claim")),
) -> schemas.InsuranceClaimRead:
    claim = await InsuranceClaimService.reject(db, company_id=company_id, claim_id=claim_id, payload=payload)
    return schemas.InsuranceClaimRead.model_validate(claim)


@router.post("/insurance-claims/{claim_id}/approve", response_model=schemas.InsuranceClaimRead)
async def approve_insurance_claim(
    claim_id: int,
    company_id: int = Depends(get_current_company_id),
    db: AsyncSession = Depends(get_db_with_tenant_context),
    actor: User = Depends(require_permission("pharmacy:insurance:claim")),
) -> schemas.InsuranceClaimRead:
    claim = await InsuranceClaimService.approve(db, company_id=company_id, claim_id=claim_id, actor_id=actor.id)
    return schemas.InsuranceClaimRead.model_validate(claim)


@router.post("/insurance-claims/{claim_id}/pay", response_model=schemas.InsuranceClaimRead)
async def pay_insurance_claim(
    claim_id: int,
    payload: schemas.InsuranceClaimPay,
    company_id: int = Depends(get_current_company_id),
    db: AsyncSession = Depends(get_db_with_tenant_context),
    actor: User = Depends(require_permission("pharmacy:insurance:claim")),
) -> schemas.InsuranceClaimRead:
    claim = await InsuranceClaimService.pay(db, company_id=company_id, claim_id=claim_id, payload=payload, actor_id=actor.id)
    return schemas.InsuranceClaimRead.model_validate(claim)
