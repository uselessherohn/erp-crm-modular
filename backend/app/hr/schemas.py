from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class EmployeeStatusEnum(str, Enum):
    active = "active"
    terminated = "terminated"


# ---------------------------------------------------------------------------
# Department
# ---------------------------------------------------------------------------


class DepartmentCreate(BaseModel):
    name: str = Field(..., max_length=150)
    parent_department_id: int | None = None


class DepartmentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    company_id: int
    name: str
    parent_department_id: int | None


# ---------------------------------------------------------------------------
# Position
# ---------------------------------------------------------------------------


class PositionCreate(BaseModel):
    title: str = Field(..., max_length=150)
    department_id: int


class PositionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    company_id: int
    title: str
    department_id: int


# ---------------------------------------------------------------------------
# Employee
# ---------------------------------------------------------------------------


class EmployeeCreate(BaseModel):
    first_name: str = Field(..., max_length=150)
    last_name: str = Field(..., max_length=150)
    email: str | None = Field(None, max_length=255)
    phone: str | None = Field(None, max_length=50)
    national_id: str | None = Field(None, max_length=50)
    position_id: int | None = None
    manager_employee_id: int | None = None
    hire_date: date
    salary: Decimal | None = Field(None, ge=0)
    user_id: int | None = None


class EmployeeTerminate(BaseModel):
    termination_date: date


class EmployeeRead(BaseModel):
    """Lectura básica — `salary` viaja como `None` si el actor no tiene
    `hr:employee:read-sensitive` (DED-21, enmascarado en el router, no acá)."""

    model_config = ConfigDict(from_attributes=True)
    id: int
    company_id: int
    user_id: int | None
    first_name: str
    last_name: str
    email: str | None
    phone: str | None
    national_id: str | None
    position_id: int | None
    manager_employee_id: int | None
    hire_date: date
    termination_date: date | None
    status: EmployeeStatusEnum
    salary: Decimal | None
    created_at: datetime
