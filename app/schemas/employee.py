from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.violation import ViolationRecordRead


class EmployeeSummary(BaseModel):
    """Row from search_employees."""
    model_config = ConfigDict(from_attributes=True)
    id: int
    employee_code: str
    full_name: str
    department: str | None = None
    position: str | None = None
    status: str
    active_violation_count: int
    total_offenses: int


class EmployeeRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    employee_code: str
    first_name: str
    last_name: str
    full_name: str
    department: str | None = None
    position: str | None = None
    status: str
    active_violation_count: int
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
    model_config = ConfigDict(extra="forbid")
    employee_code: str | None = Field(default=None, min_length=1, max_length=50)
    first_name: str | None = Field(default=None, min_length=1, max_length=100)
    last_name: str | None = Field(default=None, min_length=1, max_length=100)
    department: str | None = Field(default=None, max_length=100)
    position: str | None = Field(default=None, max_length=100)


class EmployeeTotals(BaseModel):
    employee_id: int
    active_violation_count: int
    total_offenses: int


class EmployeeDetail(EmployeeRead):
    violation_records: list[ViolationRecordRead] = Field(default_factory=list)


class BulkCreateResult(BaseModel):
    created: int
    employees: list[EmployeeRead]
