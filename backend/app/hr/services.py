"""
Servicios de hr — Fase 2.

`DepartmentService`/`PositionService` son CRUD simple. `EmployeeService`
tiene un único comportamiento no trivial: `terminate()` (baja del
empleado, status→terminated con fecha), y validaciones de integridad
referencial que Pydantic no puede expresar (posición pertenece a la
compañía, gerente no puede ser un empleado ya dado de baja, etc.).

El enmascarado de `salary` (DED-21) vive en el router, no acá — el
servicio siempre devuelve el modelo completo; es responsabilidad del
router decidir qué le llega al cliente según el permiso del actor.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.hr import models, schemas
from app.shared.exceptions import ConflictError, NotFoundError, ValidationError


class DepartmentService:
    @staticmethod
    async def create(db: AsyncSession, *, company_id: int, payload: schemas.DepartmentCreate) -> models.Department:
        if payload.parent_department_id is not None:
            await DepartmentService.get(db, company_id=company_id, department_id=payload.parent_department_id)
        department = models.Department(
            company_id=company_id, name=payload.name, parent_department_id=payload.parent_department_id
        )
        db.add(department)
        await db.commit()
        await db.refresh(department)
        return department

    @staticmethod
    async def get(db: AsyncSession, *, company_id: int, department_id: int) -> models.Department:
        result = await db.execute(
            select(models.Department).where(
                models.Department.company_id == company_id, models.Department.id == department_id
            )
        )
        department = result.scalar_one_or_none()
        if department is None:
            raise NotFoundError(f"Departamento {department_id} no encontrado")
        return department

    @staticmethod
    async def list(db: AsyncSession, *, company_id: int) -> list[models.Department]:
        result = await db.execute(select(models.Department).where(models.Department.company_id == company_id))
        return list(result.scalars().all())


class PositionService:
    @staticmethod
    async def create(db: AsyncSession, *, company_id: int, payload: schemas.PositionCreate) -> models.Position:
        await DepartmentService.get(db, company_id=company_id, department_id=payload.department_id)
        position = models.Position(company_id=company_id, title=payload.title, department_id=payload.department_id)
        db.add(position)
        await db.commit()
        await db.refresh(position)
        return position

    @staticmethod
    async def get(db: AsyncSession, *, company_id: int, position_id: int) -> models.Position:
        result = await db.execute(
            select(models.Position).where(
                models.Position.company_id == company_id, models.Position.id == position_id
            )
        )
        position = result.scalar_one_or_none()
        if position is None:
            raise NotFoundError(f"Puesto {position_id} no encontrado")
        return position

    @staticmethod
    async def list(db: AsyncSession, *, company_id: int) -> list[models.Position]:
        result = await db.execute(select(models.Position).where(models.Position.company_id == company_id))
        return list(result.scalars().all())


class EmployeeService:
    @staticmethod
    async def create(db: AsyncSession, *, company_id: int, payload: schemas.EmployeeCreate, created_by: int | None) -> models.Employee:
        if payload.position_id is not None:
            await PositionService.get(db, company_id=company_id, position_id=payload.position_id)
        if payload.manager_employee_id is not None:
            manager = await EmployeeService.get(db, company_id=company_id, employee_id=payload.manager_employee_id)
            if manager.status != "active":
                raise ValidationError("El gerente asignado no está activo")

        employee = models.Employee(
            company_id=company_id,
            user_id=payload.user_id,
            first_name=payload.first_name,
            last_name=payload.last_name,
            email=payload.email,
            phone=payload.phone,
            national_id=payload.national_id,
            position_id=payload.position_id,
            manager_employee_id=payload.manager_employee_id,
            hire_date=payload.hire_date,
            salary=payload.salary,
            created_by=created_by,
        )
        db.add(employee)
        await db.commit()
        await db.refresh(employee)
        return employee

    @staticmethod
    async def get(db: AsyncSession, *, company_id: int, employee_id: int) -> models.Employee:
        result = await db.execute(
            select(models.Employee).where(
                models.Employee.company_id == company_id, models.Employee.id == employee_id
            )
        )
        employee = result.scalar_one_or_none()
        if employee is None:
            raise NotFoundError(f"Empleado {employee_id} no encontrado")
        return employee

    @staticmethod
    async def list(db: AsyncSession, *, company_id: int) -> list[models.Employee]:
        result = await db.execute(select(models.Employee).where(models.Employee.company_id == company_id))
        return list(result.scalars().all())

    @staticmethod
    async def terminate(
        db: AsyncSession, *, company_id: int, employee_id: int, payload: schemas.EmployeeTerminate, actor_id: int | None
    ) -> models.Employee:
        result = await db.execute(
            select(models.Employee)
            .where(models.Employee.company_id == company_id, models.Employee.id == employee_id)
            .with_for_update()
        )
        employee = result.scalar_one_or_none()
        if employee is None:
            raise NotFoundError(f"Empleado {employee_id} no encontrado")
        if employee.status == "terminated":
            raise ConflictError("El empleado ya está dado de baja")
        if payload.termination_date < employee.hire_date:
            raise ValidationError("La fecha de baja no puede ser anterior a la fecha de contratación")

        employee.status = "terminated"
        employee.termination_date = payload.termination_date
        employee.updated_by = actor_id
        await db.commit()
        await db.refresh(employee)
        return employee
