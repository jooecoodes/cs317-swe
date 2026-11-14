from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Query

from app.deps import DbSession
from app.schemas.analytics import (
    ActivityBucketRow, CleanEmployeeRow, DepartmentSummaryRow,
    OffenderMetric, OffenderRow, SubsectionFrequencyRow,
    TimeBucket, WatchlistRow,
)
from queries import (
    activity_over_time, department_summary, employees_with_repeat_offenses,
    subsection_frequency, top_offenders, violation_free_employees,
)

router = APIRouter(prefix="/analytics", tags=["analytics"])


@router.get("/top-offenders", response_model=list[OffenderRow])
def offenders(
    db: DbSession,
    by: Annotated[OffenderMetric, Query()] = OffenderMetric.active,
    limit: Annotated[int, Query(ge=1, le=100)] = 10,
):
    return top_offenders(db, by=by.value, limit=limit)


@router.get("/departments", response_model=list[DepartmentSummaryRow])
def departments(db: DbSession):
    return department_summary(db)


@router.get("/subsections", response_model=list[SubsectionFrequencyRow])
def subsections(db: DbSession, limit: Annotated[int, Query(ge=1, le=100)] = 20):
    return subsection_frequency(db, limit=limit)


@router.get("/activity", response_model=list[ActivityBucketRow])
def activity(
    db: DbSession,
    days: Annotated[int, Query(ge=1, le=730)] = 30,
    bucket: Annotated[TimeBucket, Query()] = TimeBucket.day,
):
    return activity_over_time(db, days=days, bucket=bucket.value)


@router.get("/watchlist", response_model=list[WatchlistRow])
def watchlist(db: DbSession, min_offense_number: Annotated[int, Query(ge=2)] = 2):
    return employees_with_repeat_offenses(db, min_offense_number=min_offense_number)


@router.get("/clean-employees", response_model=list[CleanEmployeeRow])
def clean(db: DbSession, since: Annotated[datetime | None, Query()] = None):
    return violation_free_employees(db, since=since)
