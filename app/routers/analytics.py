from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Query

from app.deps import DbSession
from app.schemas.analytics import (
    ActivityBucketRow,
    CleanEmployeeRow,
    DepartmentSummaryRow,
    OffenderMetric,
    OffenderRow,
    TimeBucket,
    ViolationTypeFrequencyRow,
    WatchlistRow,
)
from queries import (
    activity_over_time,
    department_summary,
    employees_with_repeat_strikes,
    top_offenders,
    violation_free_employees,
    violation_type_frequency,
)

router = APIRouter(prefix="/analytics", tags=["analytics"])


@router.get("/top-offenders", response_model=list[OffenderRow])
def offenders(
    db: DbSession,
    by: Annotated[OffenderMetric, Query()] = OffenderMetric.points,
    limit: Annotated[int, Query(ge=1, le=100)] = 10,
):
    return top_offenders(db, by=by.value, limit=limit)


@router.get("/departments", response_model=list[DepartmentSummaryRow])
def departments(db: DbSession):
    return department_summary(db)


@router.get("/violation-types", response_model=list[ViolationTypeFrequencyRow])
def type_frequency(db: DbSession, limit: Annotated[int, Query(ge=1, le=100)] = 20):
    return violation_type_frequency(db, limit=limit)


@router.get("/activity", response_model=list[ActivityBucketRow])
def activity(
    db: DbSession,
    days: Annotated[int, Query(ge=1, le=730)] = 30,
    bucket: Annotated[TimeBucket, Query()] = TimeBucket.day,
):
    return activity_over_time(db, days=days, bucket=bucket.value)


@router.get("/watchlist", response_model=list[WatchlistRow])
def watchlist(db: DbSession, min_strikes: Annotated[int, Query(ge=1)] = 2):
    return employees_with_repeat_strikes(db, min_strikes=min_strikes)


@router.get("/clean-employees", response_model=list[CleanEmployeeRow])
def clean(db: DbSession, since: Annotated[datetime | None, Query()] = None):
    return violation_free_employees(db, since=since)
