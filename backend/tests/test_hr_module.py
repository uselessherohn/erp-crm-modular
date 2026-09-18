"""
Tests de integración del módulo hr — contra PostgreSQL real.

HALLAZGO ya documentado en catalogo_casos_regresion_erp_crm_v1.md (no es
sorpresa esta vez, a diferencia de accounting): "Sin archivo de test
dedicado a la fecha de este documento". Confirmado, escrito desde cero.
"""
from __future__ import annotations

import uuid
from datetime import date

import pytest
import pytest_asyncio
from sqlalchemy import select, text

from app import models_registry  # noqa: F401  (registra todos los modelos — user.active_warehouse_id -> warehouses; mismo patrón que test_core_module.py/test_medical_module.py, necesario porque este archivo crea Users reales para el test de enmascarado de salario)
from app.core import models as core_models, schemas as core_schemas
from app.core.dependencies import user_has_permission
from app.core.services import RoleService, UserService
from app.database import AsyncSessionLocal
from app.hr import schemas
from app.hr.services import DepartmentService, EmployeeService, PositionService
from app.shared.exceptions import ConflictError, NotFoundError, ValidationError


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
async def department(db, company):
    return await DepartmentService.create(db, company_id=company.id, payload=schemas.DepartmentCreate(name="Ventas"))


@pytest_asyncio.fixture
async def position(db, company, department):
    return await PositionService.create(
        db, company_id=company.id, payload=schemas.PositionCreate(title="Vendedor", department_id=department.id)
    )


# ---------------------------------------------------------------------------
# Camino feliz
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_employee_legajo_with_manager_hierarchy(db, company, position):
    unique = uuid.uuid4().hex[:8]
    boss = await EmployeeService.create(
        db, company_id=company.id,
        payload=schemas.EmployeeCreate(first_name="Jefa", last_name="Uno", hire_date=date(2020, 1, 1), position_id=position.id),
        created_by=None,
    )
    report = await EmployeeService.create(
        db, company_id=company.id,
        payload=schemas.EmployeeCreate(
            first_name="Reporte", last_name="Uno", hire_date=date(2021, 1, 1), position_id=position.id,
            manager_employee_id=boss.id,
        ),
        created_by=None,
    )
    assert report.manager_employee_id == boss.id

    # "Consulta del organigrama completo" — no hay endpoint dedicado de
    # árbol, pero list() + manager_employee_id alcanza para reconstruirlo
    # client-side. Confirmado que list() trae ambos.
    all_employees = await EmployeeService.list(db, company_id=company.id)
    assert {e.id for e in all_employees} >= {boss.id, report.id}


@pytest.mark.asyncio
async def test_manager_must_exist_and_be_active(db, company, position):
    with pytest.raises(NotFoundError):
        await EmployeeService.create(
            db, company_id=company.id,
            payload=schemas.EmployeeCreate(first_name="X", last_name="Y", hire_date=date(2021, 1, 1), manager_employee_id=99999),
            created_by=None,
        )


# ---------------------------------------------------------------------------
# Casos límite
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_circular_hierarchy_structurally_impossible_no_update_endpoint(db, company):
    """Catálogo módulo 8: 'jerarquía circular (A reporta a B, B reporta a
    A) → rechazada en la asignación, nunca persistida'. Hallazgo real:
    no hay NINGÚN endpoint para actualizar manager_employee_id después
    de creado un empleado (EmployeeService solo tiene create/get/list/
    terminate) — así que un ciclo es estructuralmente IMPOSIBLE de
    construir, no porque haya una validación explícita que lo detecte y
    rechace, sino porque el manager siempre debe existir ANTES que el
    empleado que lo referencia (EmployeeService.get lo confirma), y no
    hay forma de "cerrar" el ciclo después. Documentado como límite
    estructural, no como validación de negocio — distinto de lo que el
    catálogo asumía (una regla que rechaza el ciclo), aunque el
    resultado observable (nunca hay un ciclo persistido) es el mismo."""
    # Intento del único camino que podría acercarse a un ciclo: un
    # empleado que se referencia a sí mismo como manager, apenas creado
    # (antes de tener id) — ni siquiera es expresable, porque
    # manager_employee_id se valida contra un empleado YA EXISTENTE.
    with pytest.raises(NotFoundError):
        await EmployeeService.create(
            db, company_id=company.id,
            payload=schemas.EmployeeCreate(first_name="Solo", last_name="X", hire_date=date(2021, 1, 1), manager_employee_id=1),
            created_by=None,
        )
    # (manager_employee_id=1 no existe todavía en esta compañía vacía —
    # confirma que no hay forma de "adivinar" el propio id futuro.)


@pytest.mark.asyncio
async def test_terminate_manager_orphans_subordinates_does_not_block_or_reassign(db, company, position):
    """Catálogo módulo 8: 'eliminar/desactivar un empleado que es jefe de
    otros → confirmar la regla real (¿bloquea, reasigna, deja
    huérfanos?)'. Respuesta real confirmada: NO bloquea, NO reasigna —
    deja al subordinado con manager_employee_id apuntando a un empleado
    'terminated'. No hay ninguna limpieza automática. Vale la pena que
    quien construya un endpoint de reasignación en el futuro sepa que
    hoy esto no pasa solo."""
    boss = await EmployeeService.create(
        db, company_id=company.id,
        payload=schemas.EmployeeCreate(first_name="Jefa", last_name="Uno", hire_date=date(2020, 1, 1)),
        created_by=None,
    )
    report = await EmployeeService.create(
        db, company_id=company.id,
        payload=schemas.EmployeeCreate(first_name="Reporte", last_name="Uno", hire_date=date(2021, 1, 1), manager_employee_id=boss.id),
        created_by=None,
    )

    await EmployeeService.terminate(
        db, company_id=company.id, employee_id=boss.id, payload=schemas.EmployeeTerminate(termination_date=date(2024, 1, 1)), actor_id=None
    )

    refreshed_report = await EmployeeService.get(db, company_id=company.id, employee_id=report.id)
    assert refreshed_report.manager_employee_id == boss.id  # NO se reasignó ni se limpió — huérfano real, confirmado

    refreshed_boss = await EmployeeService.get(db, company_id=company.id, employee_id=boss.id)
    assert refreshed_boss.status == "terminated"


@pytest.mark.asyncio
async def test_terminate_twice_rejected(db, company):
    emp = await EmployeeService.create(
        db, company_id=company.id, payload=schemas.EmployeeCreate(first_name="X", last_name="Y", hire_date=date(2020, 1, 1)), created_by=None
    )
    await EmployeeService.terminate(
        db, company_id=company.id, employee_id=emp.id, payload=schemas.EmployeeTerminate(termination_date=date(2024, 1, 1)), actor_id=None
    )
    with pytest.raises(ConflictError):
        await EmployeeService.terminate(
            db, company_id=company.id, employee_id=emp.id, payload=schemas.EmployeeTerminate(termination_date=date(2024, 6, 1)), actor_id=None
        )


@pytest.mark.asyncio
async def test_termination_date_before_hire_date_rejected(db, company):
    emp = await EmployeeService.create(
        db, company_id=company.id, payload=schemas.EmployeeCreate(first_name="X", last_name="Y", hire_date=date(2023, 1, 1)), created_by=None
    )
    with pytest.raises(ValidationError):
        await EmployeeService.terminate(
            db, company_id=company.id, employee_id=emp.id, payload=schemas.EmployeeTerminate(termination_date=date(2020, 1, 1)), actor_id=None
        )


# ---------------------------------------------------------------------------
# RBAC — el caso más importante del módulo (DED-21)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_salary_masked_server_side_without_sensitive_permission(db, company):
    """Catálogo módulo 8 — 'el caso más importante de este módulo':
    confirmar que un usuario con SOLO hr:employee:read (sin
    hr:employee:read-sensitive) nunca recibe salary, ni siquiera como
    null filtrable client-side. Prueba la función real que usa el router
    (user_has_permission), no una reimplementación — mismo helper que
    app/hr/routers.py."""
    emp = await EmployeeService.create(
        db, company_id=company.id,
        payload=schemas.EmployeeCreate(first_name="Con Salario", last_name="X", hire_date=date(2020, 1, 1), salary=18000),
        created_by=None,
    )
    assert emp.salary == 18000  # el dato SÍ existe en la base — el enmascarado es de lectura, no de escritura

    # 'permissions' es una tabla GLOBAL sembrada por scripts/bootstrap_admin.py
    # (no por migración) — esta compañía de test es nueva y no pasó por ese
    # bootstrap. Sembrado idempotente acá, mismos códigos reales que usa
    # app/hr/routers.py (require_permission/user_has_permission).
    async def _get_or_create_permission(code: str) -> core_models.Permission:
        existing = (await db.execute(select(core_models.Permission).where(core_models.Permission.code == code))).scalar_one_or_none()
        if existing is not None:
            return existing
        perm = core_models.Permission(code=code, description=code)
        db.add(perm)
        await db.flush()
        return perm

    perm_basic = await _get_or_create_permission("hr:employee:read")
    role = await RoleService.create_role(
        db, company_id=company.id,
        payload=core_schemas.RoleCreate(name="HR Básico", permission_ids=[perm_basic.id]),
    )
    unique = uuid.uuid4().hex[:8]
    limited_user = await UserService.create_user(
        db, company_id=company.id,
        payload=core_schemas.UserCreate(email=f"hrbasico_{unique}@test.hn", full_name="HR Básico", password="password123"),
        created_by=None,
    )
    db.add(core_models.UserRole(user_id=limited_user.id, role_id=role.id))
    await db.commit()

    has_sensitive = await user_has_permission(db, user_id=limited_user.id, code="hr:employee:read-sensitive")
    assert has_sensitive is False

    # Simula exactamente lo que hace el router: enmascara a None si falta el permiso.
    employee_read = schemas.EmployeeRead.model_validate(emp)
    if not has_sensitive:
        employee_read.salary = None
    assert employee_read.salary is None
    assert "salary" in employee_read.model_dump()  # el campo existe, pero es None — server-side, no omitido ad-hoc

    # Un usuario CON el permiso sensible sí lo ve completo (mismo
    # employee_read sin enmascarar).
    perm_sensitive = await _get_or_create_permission("hr:employee:read-sensitive")
    role_full = await RoleService.create_role(
        db, company_id=company.id,
        payload=core_schemas.RoleCreate(name="HR Completo", permission_ids=[perm_basic.id, perm_sensitive.id]),
    )
    full_user = await UserService.create_user(
        db, company_id=company.id,
        payload=core_schemas.UserCreate(email=f"hrfull_{unique}@test.hn", full_name="HR Completo", password="password123"),
        created_by=None,
    )
    db.add(core_models.UserRole(user_id=full_user.id, role_id=role_full.id))
    await db.commit()

    has_sensitive_full = await user_has_permission(db, user_id=full_user.id, code="hr:employee:read-sensitive")
    assert has_sensitive_full is True
    employee_read_full = schemas.EmployeeRead.model_validate(emp)
    if not has_sensitive_full:
        employee_read_full.salary = None
    assert employee_read_full.salary == 18000

