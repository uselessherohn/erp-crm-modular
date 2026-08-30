from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class OpportunityStatusEnum(str, Enum):
    open = "open"
    won = "won"
    lost = "lost"


class ActivityTypeEnum(str, Enum):
    call = "call"
    email = "email"
    meeting = "meeting"
    note = "note"
    task = "task"


# ---------------------------------------------------------------------------
# Stage
# ---------------------------------------------------------------------------


class StageCreate(BaseModel):
    name: str = Field(..., max_length=100)
    sort_order: int = 0
    is_won: bool = False
    is_lost: bool = False


class StageRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    company_id: int
    name: str
    sort_order: int
    is_won: bool
    is_lost: bool
    is_active: bool


# ---------------------------------------------------------------------------
# Opportunity
# ---------------------------------------------------------------------------


class OpportunityCreate(BaseModel):
    contact_id: int
    stage_id: int
    name: str = Field(..., max_length=300)
    amount: Decimal | None = Field(None, ge=0)
    currency_code: str = Field(default="HNL", max_length=3)
    expected_close_date: date | None = None
    owner_user_id: int | None = None


class OpportunityMoveStage(BaseModel):
    stage_id: int


class OpportunityCloseLost(BaseModel):
    lost_reason: str | None = Field(None, max_length=500)


class OpportunityRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    company_id: int
    contact_id: int
    stage_id: int
    owner_user_id: int | None
    name: str
    amount: Decimal | None
    currency_code: str
    expected_close_date: date | None
    status: OpportunityStatusEnum
    closed_at: datetime | None
    lost_reason: str | None
    version: int
    created_at: datetime


# ---------------------------------------------------------------------------
# Activity
# ---------------------------------------------------------------------------


class ActivityCreate(BaseModel):
    contact_id: int
    opportunity_id: int | None = None
    activity_type: ActivityTypeEnum
    subject: str = Field(..., max_length=300)
    notes: str | None = Field(None, max_length=2000)
    due_date: date | None = None


class ActivityRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    company_id: int
    contact_id: int
    opportunity_id: int | None
    activity_type: ActivityTypeEnum
    subject: str
    notes: str | None
    due_date: date | None
    completed_at: datetime | None
    created_at: datetime
