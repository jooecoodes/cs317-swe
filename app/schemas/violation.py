from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, computed_field


class ViolationTypeRef(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    default_points: int
    is_strike: bool


class EmployeeRef(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    employee_code: str
    full_name: str


class ViolationTypeCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=100)
    description: str | None = None
    default_points: int = Field(default=0, ge=0)
    is_strike: bool = False
    is_active: bool = True


class ViolationTypeUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=100)
    description: str | None = None
    default_points: int | None = Field(default=None, ge=0)
    is_strike: bool | None = None


class ViolationTypeOption(BaseModel):
    """Row from get_active_violation_types — dropdown shape."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    default_points: int
    is_strike: bool


class ViolationTypeRead(BaseModel):
    """ORM ViolationType, full row."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: str | None = None
    default_points: int
    is_strike: bool
    is_active: bool


class ViolationAssign(BaseModel):
    model_config = ConfigDict(extra="forbid")

    violation_type_id: int = Field(ge=1)
    notes: str | None = None
    issued_by: str | None = None
    issued_at: datetime | None = None


class ViolationRecordUpdate(BaseModel):
    """Only notes / issued_by / issued_at. points and employee_id are
    not editable — they're the snapshot."""

    model_config = ConfigDict(extra="forbid")

    notes: str | None = None
    issued_by: str | None = None
    issued_at: datetime | None = None


class ViolationRecordRead(BaseModel):
    """ORM ViolationRecord with violation_type eagerly loaded."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    employee_id: int
    violation_type_id: int
    points: int
    is_strike: bool
    notes: str | None = None
    issued_by: str | None = None
    issued_at: datetime
    created_at: datetime | None = None
    violation_type: ViolationTypeRef | None = None

    @computed_field  # type: ignore[prop-decorator]
    @property
    def violation_type_name(self) -> str | None:
        return self.violation_type.name if self.violation_type else None


class ViolationRecordFeedRead(ViolationRecordRead):
    """Same as above, plus employee — used only by list_recent_violations."""

    employee: EmployeeRef | None = None
