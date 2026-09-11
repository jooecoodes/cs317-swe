from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.violation import ViolationRecordRead


class EmployeeSummary(BaseModel):
    """Row from search_employees (SQLAlchemy Row, not ORM)."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    employee_code: str
    full_name: str
    department: str | None = None
    position: str | None = None
    status: str
    total_points: int
    total_strikes: int


class EmployeeRead(BaseModel):
    """ORM Employee, full profile."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    employee_code: str
    first_name: str
    last_name: str
    full_name: str
    department: str | None = None
    position: str | None = None
    status: str
    total_points: int
    total_strikes: int
    created_at: datetime | None = None
    updated_at: datetime | None = None


class EmployeeCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    employee_code: str = Field(min_length=1, max_length=50)
    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)
    department: str | None = Field(default=None, max_length=100)
    position: str | None = Field(default=None, max_length=100)


class EmployeeUpdate(BaseModel):
    """PATCH body. Query's update_employee only applies non-None fields,
    so explicit nulls are no-ops (DB dev's semantics)."""

    model_config = ConfigDict(extra="forbid")

    employee_code: str | None = Field(default=None, min_length=1, max_length=50)
    first_name: str | None = Field(default=None, min_length=1, max_length=100)
    last_name: str | None = Field(default=None, min_length=1, max_length=100)
    department: str | None = Field(default=None, max_length=100)
    position: str | None = Field(default=None, max_length=100)


class EmployeeTotals(BaseModel):
    """Dict from get_employee_totals."""

    model_config = ConfigDict(from_attributes=True)

    employee_id: int
    total_points: int
    total_strikes: int
    total_records: int


class EmployeeDetail(EmployeeRead):
    """ORM Employee with violation_records eagerly loaded.
    Totals are hybrids on the employee — no nested sub-object."""

    violation_records: list[ViolationRecordRead] = Field(default_factory=list)


class BulkCreateResult(BaseModel):
    """create_employees_bulk is all-or-nothing: either all N succeeded,
    or the request raised DuplicateEmployeeCode."""

    created: int
    employees: list[EmployeeRead]
