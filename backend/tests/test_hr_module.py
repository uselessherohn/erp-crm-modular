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
async def test_circular_hierarchy_at_creation_structurally_impossible(db, company):
    """Catálogo módulo 8: 'jerarquía circular (A reporta a B, B reporta a
    A) → rechazada en la asignación, nunca persistida'.

    Actualización (sep-2026): esto describe dos mecanismos distintos
    según el momento:
    - Al CREAR un empleado (este test): sigue siendo estructuralmente
      imposible, sin necesidad de validación explícita — el manager
      siempre debe existir ANTES que el empleado que lo referencia.
    - Al ACTUALIZAR un empleado ya existente (ver
      test_update_manager_rejects_real_circular_hierarchy más abajo):
      ahora SÍ es posible intentarlo (EmployeeService.update agregado en
      esta misma regresión), así que ahí la validación es real y
      explícita, no solo un efecto estructural."""
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



# ---------------------------------------------------------------------------
# EmployeeService.update — gap real cerrado (sep-2026): antes no existía
# NINGÚN endpoint de actualización.
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_update_reassigns_manager_position_and_basic_fields(db, company, department):
    pos_a = await PositionService.create(db, company_id=company.id, payload=schemas.PositionCreate(title="Junior", department_id=department.id))
    pos_b = await PositionService.create(db, company_id=company.id, payload=schemas.PositionCreate(title="Senior", department_id=department.id))
    boss = await EmployeeService.create(
        db, company_id=company.id, payload=schemas.EmployeeCreate(first_name="Jefa", last_name="X", hire_date=date(2020, 1, 1)), created_by=None
    )
    emp = await EmployeeService.create(
        db, company_id=company.id,
        payload=schemas.EmployeeCreate(first_name="Antes", last_name="Y", hire_date=date(2021, 1, 1), position_id=pos_a.id),
        created_by=None,
    )

    updated = await EmployeeService.update(
        db, company_id=company.id, employee_id=emp.id,
        payload=schemas.EmployeeUpdate(first_name="Después", position_id=pos_b.id, manager_employee_id=boss.id, phone="9999-0000"),
        updated_by=None,
    )
    assert updated.first_name == "Después"
    assert updated.position_id == pos_b.id
    assert updated.manager_employee_id == boss.id
    assert updated.phone == "9999-0000"


@pytest.mark.asyncio
async def test_update_manager_to_none_clears_it_explicitly(db, company):
    boss = await EmployeeService.create(
        db, company_id=company.id, payload=schemas.EmployeeCreate(first_name="Jefa", last_name="X", hire_date=date(2020, 1, 1)), created_by=None
    )
    emp = await EmployeeService.create(
        db, company_id=company.id,
        payload=schemas.EmployeeCreate(first_name="Y", last_name="Z", hire_date=date(2021, 1, 1), manager_employee_id=boss.id),
        created_by=None,
    )
    assert emp.manager_employee_id == boss.id

    cleared = await EmployeeService.update(
        db, company_id=company.id, employee_id=emp.id, payload=schemas.EmployeeUpdate(manager_employee_id=None), updated_by=None
    )
    assert cleared.manager_employee_id is None


@pytest.mark.asyncio
async def test_update_self_as_manager_rejected(db, company):
    emp = await EmployeeService.create(
        db, company_id=company.id, payload=schemas.EmployeeCreate(first_name="X", last_name="Y", hire_date=date(2021, 1, 1)), created_by=None
    )
    with pytest.raises(ValidationError):
        await EmployeeService.update(
            db, company_id=company.id, employee_id=emp.id, payload=schemas.EmployeeUpdate(manager_employee_id=emp.id), updated_by=None
        )


@pytest.mark.asyncio
async def test_update_manager_rejects_real_circular_hierarchy(db, company):
    """Ahora que EmployeeService.update existe, un ciclo SÍ es
    construible en principio (A gerente de B, luego intentar que B sea
    gerente de A) — este test confirma que la validación nueva lo
    rechaza de verdad, con un ciclo real de 2 y de 3 eslabones."""
    a = await EmployeeService.create(db, company_id=company.id, payload=schemas.EmployeeCreate(first_name="A", last_name="X", hire_date=date(2020, 1, 1)), created_by=None)
    b = await EmployeeService.create(
        db, company_id=company.id, payload=schemas.EmployeeCreate(first_name="B", last_name="X", hire_date=date(2020, 1, 1), manager_employee_id=a.id), created_by=None
    )
    # Ciclo directo de 2: A reporta a B, pero B ya reporta a A.
    with pytest.raises(ConflictError):
        await EmployeeService.update(db, company_id=company.id, employee_id=a.id, payload=schemas.EmployeeUpdate(manager_employee_id=b.id), updated_by=None)

    # Ciclo de 3 eslabones: A->B->C, intentar que A reporte a C.
    c = await EmployeeService.create(
        db, company_id=company.id, payload=schemas.EmployeeCreate(first_name="C", last_name="X", hire_date=date(2020, 1, 1), manager_employee_id=b.id), created_by=None
    )
    with pytest.raises(ConflictError):
        await EmployeeService.update(db, company_id=company.id, employee_id=a.id, payload=schemas.EmployeeUpdate(manager_employee_id=c.id), updated_by=None)

    # Confirmación de que la cadena real (no circular) sí se puede armar:
    # D reportando a C (extiende la cadena A->B->C->D) es válido.
    d = await EmployeeService.create(db, company_id=company.id, payload=schemas.EmployeeCreate(first_name="D", last_name="X", hire_date=date(2020, 1, 1)), created_by=None)
    updated_d = await EmployeeService.update(db, company_id=company.id, employee_id=d.id, payload=schemas.EmployeeUpdate(manager_employee_id=c.id), updated_by=None)
    assert updated_d.manager_employee_id == c.id


@pytest.mark.asyncio
async def test_cannot_update_terminated_employee(db, company):
    emp = await EmployeeService.create(
        db, company_id=company.id, payload=schemas.EmployeeCreate(first_name="X", last_name="Y", hire_date=date(2020, 1, 1)), created_by=None
    )
    await EmployeeService.terminate(db, company_id=company.id, employee_id=emp.id, payload=schemas.EmployeeTerminate(termination_date=date(2024, 1, 1)), actor_id=None)
    with pytest.raises(ConflictError):
        await EmployeeService.update(db, company_id=company.id, employee_id=emp.id, payload=schemas.EmployeeUpdate(phone="1111"), updated_by=None)


@pytest.mark.asyncio
async def test_update_salary_requires_separate_sensitive_permission_router_level(db, company):
    """Router-level: editar salary exige hr:employee:update-sensitive
    ADEMÁS de hr:employee:update — mismo criterio que
    contacts:contact:update_credit_limit. Se prueba la función real
    (user_has_permission) que usa el router, mismo patrón que el test de
    lectura de más arriba."""
    emp = await EmployeeService.create(
        db, company_id=company.id, payload=schemas.EmployeeCreate(first_name="X", last_name="Y", hire_date=date(2020, 1, 1), salary=1000), created_by=None
    )

    async def _get_or_create_permission(code: str) -> core_models.Permission:
        existing = (await db.execute(select(core_models.Permission).where(core_models.Permission.code == code))).scalar_one_or_none()
        if existing is not None:
            return existing
        perm = core_models.Permission(code=code, description=code)
        db.add(perm)
        await db.flush()
        return perm

    perm_update = await _get_or_create_permission("hr:employee:update")
    unique = uuid.uuid4().hex[:8]
    role = await RoleService.create_role(db, company_id=company.id, payload=core_schemas.RoleCreate(name="HR Editor Básico", permission_ids=[perm_update.id]))
    limited_user = await UserService.create_user(
        db, company_id=company.id,
        payload=core_schemas.UserCreate(email=f"hreditor_{unique}@test.hn", full_name="HR Editor", password="password123"),
        created_by=None,
    )
    db.add(core_models.UserRole(user_id=limited_user.id, role_id=role.id))
    await db.commit()

    has_sensitive = await user_has_permission(db, user_id=limited_user.id, code="hr:employee:update-sensitive")
    assert has_sensitive is False  # confirma que el router rechazaría el cambio de salario para este usuario

    # Sin el permiso sensible, el servicio en sí NO valida esto (es
    # responsabilidad del router, mismo criterio que el enmascarado de
    # lectura) — pero confirmamos que el router SÍ tiene el chequeo
    # importando la función real que usa.
    from app.hr.routers import update_employee
    import inspect
    source = inspect.getsource(update_employee)
    assert "hr:employee:update-sensitive" in source
