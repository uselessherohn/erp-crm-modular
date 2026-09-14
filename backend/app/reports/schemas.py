from __future__ import annotations

from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class MetricInfo(BaseModel):
    key: str
    label: str
    columns: list[str]


class MetricDataRequest(BaseModel):
    date_from: date
    date_to: date

    @field_validator("date_to")
    @classmethod
    def validate_range(cls, date_to: date, info) -> date:
        date_from = info.data.get("date_from")
        if date_from is not None and date_to < date_from:
            raise ValueError("date_to no puede ser anterior a date_from")
        return date_to


class MetricDataResult(BaseModel):
    key: str
    columns: list[str]
    rows: list[dict[str, Any]]


class DashboardWidget(BaseModel):
    widget_type: str = Field(default="table", pattern="^(table|metric)$")
    metric_key: str
    title: str = Field(..., max_length=200)


class DashboardCreate(BaseModel):
    name: str = Field(..., max_length=200)
    widgets: list[DashboardWidget] = Field(default_factory=list)


class DashboardUpdate(BaseModel):
    name: str | None = Field(None, max_length=200)
    widgets: list[DashboardWidget] | None = None


class DashboardRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    company_id: int
    name: str
    owner_user_id: int | None
    widgets: list[DashboardWidget]
    created_at: datetime
    updated_at: datetime
