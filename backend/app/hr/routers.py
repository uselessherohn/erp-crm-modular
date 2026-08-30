"""
Routers de hr. DED-21: `salary` se enmascara a `None` en la respuesta de
`EmployeeRead` si el actor no tiene `hr:employee:read-sensitive`, además
del permiso básico `hr:employee:read` — chequeo "suave" vía
`user_has_permission()` (core), no bloquea la request completa.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_company_id, get_db_with_tenant_context, require_permission, user_has_permission
from app.core.models import User
from app.hr import schemas
from app.hr.services import DepartmentService, EmployeeService, PositionService

router = APIRouter(prefix="/hr", tags=["hr"])


async def _mask_sensitive(db: AsyncSession, *, actor: User, employee: schemas.EmployeeRead) -> schemas.EmployeeRead:
    if not await user_has_permission(db, user_id=actor.id, code="hr:employee:read-sensitive"):
        employee.salary = None
    return employee


# ---------------------------------------------------------------------------
# Departments
# ---------------------------------------------------------------------------
@router.post("/departments", response_model=schemas.DepartmentRead, status_code=201)
async def create_department(
    payload: schemas.DepartmentCreate,
    company_id: int = Depends(get_current_company_id),
    db: AsyncSession = Depends(get_db_with_tenant_context),
    _actor: User = Depends(require_permission("hr:department:create")),
) -> schemas.DepartmentRead:
    department = await DepartmentService.create(db, company_id=company_id, payload=payload)
    return schemas.DepartmentRead.model_validate(department)


@router.get("/departments", response_model=list[schemas.DepartmentRead])
async def list_departments(
    company_id: int = Depends(get_current_company_id),
    db: AsyncSession = Depends(get_db_with_tenant_context),
    _actor: User = Depends(require_permission("hr:department:list")),
) -> list[schemas.DepartmentRead]:
    return [schemas.DepartmentRead.model_validate(d) for d in await DepartmentService.list(db, company_id=company_id)]


# ---------------------------------------------------------------------------
# Positions
# ---------------------------------------------------------------------------
@router.post("/positions", response_model=schemas.PositionRead, status_code=201)
async def create_position(
    payload: schemas.PositionCreate,
    company_id: int = Depends(get_current_company_id),
    db: AsyncSession = Depends(get_db_with_tenant_context),
    _actor: User = Depends(require_permission("hr:position:create")),
) -> schemas.PositionRead:
    position = await PositionService.create(db, company_id=company_id, payload=payload)
    return schemas.PositionRead.model_validate(position)


@router.get("/positions", response_model=list[schemas.PositionRead])
async def list_positions(
    company_id: int = Depends(get_current_company_id),
    db: AsyncSession = Depends(get_db_with_tenant_context),
    _actor: User = Depends(require_permission("hr:position:list")),
) -> list[schemas.PositionRead]:
    return [schemas.PositionRead.model_validate(p) for p in await PositionService.list(db, company_id=company_id)]


# ---------------------------------------------------------------------------
# Employees
# ---------------------------------------------------------------------------
@router.post("/employees", response_model=schemas.EmployeeRead, status_code=201)
async def create_employee(
    payload: schemas.EmployeeCreate,
    company_id: int = Depends(get_current_company_id),
    db: AsyncSession = Depends(get_db_with_tenant_context),
    actor: User = Depends(require_permission("hr:employee:create")),
) -> schemas.EmployeeRead:
    employee = await EmployeeService.create(db, company_id=company_id, payload=payload, created_by=actor.id)
    return await _mask_sensitive(db, actor=actor, employee=schemas.EmployeeRead.model_validate(employee))


@router.get("/employees", response_model=list[schemas.EmployeeRead])
async def list_employees(
    company_id: int = Depends(get_current_company_id),
    db: AsyncSession = Depends(get_db_with_tenant_context),
    actor: User = Depends(require_permission("hr:employee:read")),
) -> list[schemas.EmployeeRead]:
    employees = [schemas.EmployeeRead.model_validate(e) for e in await EmployeeService.list(db, company_id=company_id)]
    has_sensitive = await user_has_permission(db, user_id=actor.id, code="hr:employee:read-sensitive")
    if not has_sensitive:
        for e in employees:
            e.salary = None
    return employees


@router.get("/employees/{employee_id}", response_model=schemas.EmployeeRead)
async def get_employee(
    employee_id: int,
    company_id: int = Depends(get_current_company_id),
    db: AsyncSession = Depends(get_db_with_tenant_context),
    actor: User = Depends(require_permission("hr:employee:read")),
) -> schemas.EmployeeRead:
    employee = await EmployeeService.get(db, company_id=company_id, employee_id=employee_id)
    return await _mask_sensitive(db, actor=actor, employee=schemas.EmployeeRead.model_validate(employee))


@router.post("/employees/{employee_id}/terminate", response_model=schemas.EmployeeRead)
async def terminate_employee(
    employee_id: int,
    payload: schemas.EmployeeTerminate,
    company_id: int = Depends(get_current_company_id),
    db: AsyncSession = Depends(get_db_with_tenant_context),
    actor: User = Depends(require_permission("hr:employee:terminate")),
) -> schemas.EmployeeRead:
    employee = await EmployeeService.terminate(db, company_id=company_id, employee_id=employee_id, payload=payload, actor_id=actor.id)
    return await _mask_sensitive(db, actor=actor, employee=schemas.EmployeeRead.model_validate(employee))
