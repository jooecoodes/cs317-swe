from enum import Enum

from pydantic import BaseModel, ConfigDict


class OffenderMetric(str, Enum):
    points = "points"
    strikes = "strikes"
    records = "records"


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
    total_points: int
    total_strikes: int


class DepartmentSummaryRow(BaseModel):
    """Plain dicts from department_summary()."""

    model_config = ConfigDict(from_attributes=True)

    department: str | None
    employees: int
    total_points: int
    total_records: int
    total_strikes: int


class ViolationTypeFrequencyRow(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    default_points: int
    is_strike: bool
    times_issued: int
    total_points: int


class ActivityBucketRow(BaseModel):
    """bucket is a string like '2026-09-11'. Gaps are not filled."""

    model_config = ConfigDict(from_attributes=True)

    bucket: str
    count: int
    points: int


class WatchlistRow(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    employee_code: str
    full_name: str
    department: str | None = None
    total_strikes: int
    total_points: int


class CleanEmployeeRow(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    employee_code: str
    full_name: str
    department: str | None = None
