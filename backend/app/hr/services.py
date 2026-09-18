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
    async def update(
        db: AsyncSession, *, company_id: int, employee_id: int, payload: schemas.EmployeeUpdate, updated_by: int | None
    ) -> models.Employee:
        """Hallazgo real de la regresión QA externa (sep-2026): no existía
        forma de reasignar `manager_employee_id`/`position_id`/`salary`
        después de creado un empleado. Al agregar esto, la jerarquía
        circular (catálogo módulo 8) deja de ser estructuralmente
        imposible — así que ACÁ es donde corresponde la validación real
        que antes no hacía falta: recorrer la cadena de managers hacia
        arriba desde el candidato y rechazar si se vuelve a llegar al
        propio empleado (o si el candidato ES el propio empleado)."""
        employee = await EmployeeService.get(db, company_id=company_id, employee_id=employee_id)
        if employee.status != "active":
            raise ConflictError("No se puede editar un empleado dado de baja")

        changes = payload.model_dump(exclude_unset=True)

        if "position_id" in changes and changes["position_id"] is not None:
            await PositionService.get(db, company_id=company_id, position_id=changes["position_id"])

        if "manager_employee_id" in changes and changes["manager_employee_id"] is not None:
            new_manager_id = changes["manager_employee_id"]
            if new_manager_id == employee_id:
                raise ValidationError("Un empleado no puede ser su propio gerente")
            manager = await EmployeeService.get(db, company_id=company_id, employee_id=new_manager_id)
            if manager.status != "active":
                raise ValidationError("El gerente asignado no está activo")

            # Recorrido hacia arriba: si en algún punto de la cadena de
            # managers del candidato aparece el propio employee_id, sería
            # un ciclo (spec 8.1, catálogo módulo 8, "jerarquía circular").
            cursor = manager
            visited: set[int] = set()
            while cursor.manager_employee_id is not None:
                if cursor.manager_employee_id == employee_id:
                    raise ConflictError(
                        f"Asignación rechazada: crearía una jerarquía circular "
                        f"(el empleado {employee_id} terminaría reportándose a sí mismo, "
                        f"vía la cadena de gerentes de {new_manager_id})"
                    )
                if cursor.id in visited:
                    break  # defensa extra: no debería haber ciclos preexistentes, pero no loopear infinito si los hay
                visited.add(cursor.id)
                cursor = await EmployeeService.get(db, company_id=company_id, employee_id=cursor.manager_employee_id)

        for field, value in changes.items():
            setattr(employee, field, value)
        employee.updated_by = updated_by
        await db.commit()
        await db.refresh(employee)
        return employee

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
