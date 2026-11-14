from enum import Enum

from pydantic import BaseModel, ConfigDict


class OffenderMetric(str, Enum):
    active = "active"
    total = "total"


class TimeBucket(str, Enum):
    day = "day"
    week = "week"
    month = "month"


class OffenderRow(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    employee_code: str
    full_name: str
    department: str | None = None
    active_violation_count: int
    total_offenses: int


class DepartmentSummaryRow(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    department: str | None
    employees: int
    active_violations: int


class SubsectionFrequencyRow(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    subsection_name: str
    violation_type_name: str
    times_issued: int
    max_offense_number: int | None = None


class ActivityBucketRow(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    bucket: str
    count: int


class WatchlistRow(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    employee_code: str
    full_name: str
    department: str | None = None
    max_offense: int
    total_offenses: int


class CleanEmployeeRow(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    employee_code: str
    full_name: str
    department: str | None = None
