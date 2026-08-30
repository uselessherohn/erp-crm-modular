"""
Módulo 8 — hr (spec 8.1, subset [core]): Legajo, Estructura
Organizacional, Jerarquías.

[extendido] fuera de este cierre: Nómina/Payroll (agrega dependencia real
de `accounting` — spec: "si se incluye, agrega dependencia de accounting,
debe construirse después"; como `accounting` ya está construido no hay
bloqueo técnico, pero Payroll en sí mismo es un motor con su propia
complejidad — cálculo de deducciones, aportes patronales, generación de
asientos — no se construye acá), Control de Asistencia y Horarios,
Ausencias y Vacaciones, Evaluación de Desempeño, Reclutamiento.

DECISIONES DEDUCIBLE/AMBIGUO de este módulo (registro formal en STATE.md
sección 4; resumen acá):

- DED-20: `Employee` se modela como entidad propia, NO reutiliza
  `Contact` — a diferencia de "Lead" (que sí reutiliza `Contact.is_lead`),
  un empleado no es un contacto de negocio (cliente/proveedor/paciente/
  lead) y `Contact` no tiene ningún flag `is_employee`. Vínculo opcional a
  `User` (cuenta de acceso al sistema) vía `user_id` nullable, para el
  caso común de que el propio dueño/admin también sea empleado — no todo
  empleado necesita una cuenta de login (ej. personal de bodega).
- DED-21: datos sensibles (spec 8.1: "salario, evaluaciones requieren
  RBAC estricto") — permiso separado `hr:employee:read-sensitive` (ve
  `salary`) vs `hr:employee:read` (ve el resto del legajo). El salario se
  enmascara (`None`) en la respuesta si el actor no tiene el permiso
  sensible, verificado en el router vía `user_has_permission()` (nuevo
  helper reutilizable en `core`), no en el modelo ni en constraints DB.
- DED-22: "Jerarquías" se modela con dos relaciones self-referenciales
  independientes — `Department.parent_department_id` (estructura
  organizacional) y `Employee.manager_employee_id` (línea de reporte) —
  spec no exige que coincidan (un empleado puede reportar a alguien de
  otro departamento).
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
    Numeric,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class EmployeeStatusEnum(str, enum.Enum):
    active = "active"
    terminated = "terminated"


EMPLOYEE_STATUSES = tuple(s.value for s in EmployeeStatusEnum)


class Department(Base):
    __tablename__ = "departments"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    company_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("companies.id"), nullable=False, index=True)

    name: Mapped[str] = mapped_column(String(150), nullable=False)
    parent_department_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("departments.id"), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        UniqueConstraint("company_id", "name", name="uq_departments_company_name"),
        CheckConstraint("parent_department_id IS NULL OR parent_department_id <> id", name="ck_departments_not_own_parent"),
    )


class Position(Base):
    __tablename__ = "positions"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    company_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("companies.id"), nullable=False, index=True)

    title: Mapped[str] = mapped_column(String(150), nullable=False)
    department_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("departments.id"), nullable=False, index=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        UniqueConstraint("company_id", "department_id", "title", name="uq_positions_company_department_title"),
    )


class Employee(Base):
    """Legajo — DED-20: entidad propia, no reutiliza Contact."""

    __tablename__ = "employees"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    company_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("companies.id"), nullable=False, index=True)

    # Vínculo opcional a la cuenta de login (DED-20) — no todo empleado
    # tiene acceso al sistema.
    user_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("users.id"), nullable=True)

    first_name: Mapped[str] = mapped_column(String(150), nullable=False)
    last_name: Mapped[str] = mapped_column(String(150), nullable=False)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    national_id: Mapped[str | None] = mapped_column(String(50), nullable=True)

    position_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("positions.id"), nullable=True)
    # Jerarquías (DED-22) — independiente de la estructura organizacional
    # de Department; un empleado puede reportar a alguien de otro depto.
    manager_employee_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("employees.id"), nullable=True)

    hire_date: Mapped[date] = mapped_column(Date, nullable=False)
    termination_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="active")

    # salary: dato sensible (DED-21) — enmascarado en la respuesta si el
    # actor no tiene hr:employee:read-sensitive, verificado en el router.
    salary: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    created_by: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("users.id"), nullable=True)
    updated_by: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("users.id"), nullable=True)

    __table_args__ = (
        UniqueConstraint("company_id", "user_id", name="uq_employees_company_user"),
        CheckConstraint(f"status IN {EMPLOYEE_STATUSES}", name="ck_employees_status"),
        CheckConstraint("salary IS NULL OR salary >= 0", name="ck_employees_salary_nonneg"),
        CheckConstraint("manager_employee_id IS NULL OR manager_employee_id <> id", name="ck_employees_not_own_manager"),
    )
