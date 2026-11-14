from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


# ---------- violation types ----------

class ViolationTypeCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=150)
    description: str | None = None
    is_active: bool = True


class ViolationTypeUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str | None = Field(default=None, min_length=1, max_length=150)
    description: str | None = None


class ViolationTypeOption(BaseModel):
    """Dropdown shape — GET /violation-types."""
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    description: str | None = None


class ViolationTypeRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    description: str | None = None
    is_active: bool


# ---------- penalties ----------

class PenaltyInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    offense_number: int = Field(ge=1)
    description: str = Field(min_length=1)


class PenaltyRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    offense_number: int
    description: str


class PenaltyReplaceBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    penalties: list[PenaltyInput]


# ---------- subsections ----------

class SubsectionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=300)
    description: str | None = None
    is_active: bool = True


class SubsectionUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str | None = Field(default=None, min_length=1, max_length=300)
    description: str | None = None


class SubsectionOption(BaseModel):
    """Dropdown shape — GET /violation-types/{id}/subsections."""
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    description: str | None = None


class SubsectionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    violation_type_id: int
    name: str
    description: str | None = None
    is_active: bool
    penalties: list[PenaltyRead] = Field(default_factory=list)


# ---------- violation records ----------

class ViolationAssign(BaseModel):
    """Body for POST /employees/{id}/violations. Subsection replaces type."""

    model_config = ConfigDict(extra="forbid")
    subsection_id: int = Field(ge=1)
    notes: str | None = None
    issued_by: str | None = None
    issued_at: datetime | None = None


class ViolationRecordUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    notes: str | None = None
    issued_by: str | None = None
    issued_at: datetime | None = None


class SubsectionRef(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    violation_type_id: int


class ViolationTypeRef(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str


class EmployeeRef(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    employee_code: str
    full_name: str


class ViolationRecordRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    employee_id: int
    subsection_id: int
    offense_number: int
    penalty_description: str | None = None
    notes: str | None = None
    issued_by: str | None = None
    issued_at: datetime
    created_at: datetime | None = None

    subsection: SubsectionRef | None = None


class ViolationRecordFeedRead(ViolationRecordRead):
    """Used by /violations/recent — includes employee."""

    employee: EmployeeRef | None = None


# ---------- employee offense summary (bonus view) ----------

class EmployeeOffenseSummaryRow(BaseModel):
    subsection_id: int
    subsection_name: str
    violation_type_name: str
    active_offenses: int
    removed_offenses: int
    total_offenses: int
    last_offense_number: int
    next_offense_number: int
    penalty_if_repeated: str | None = None
