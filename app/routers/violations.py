from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, HTTPException, Path, Query, status
from pydantic import BaseModel

from app.deps import ActorDep, DbSession, PaginationDep
from app.schemas.removal import ViolationRemovalCreate, ViolationRemovalRead
from app.schemas.violation import (
    EmployeeOffenseSummaryRow, ViolationAssign,
    ViolationRecordFeedRead, ViolationRecordRead, ViolationRecordUpdate,
)
from queries import (
    assign_violation, clear_employee_violations, get_employee_offense_summary,
    get_violation_record, list_employee_violations, list_recent_violations,
    remove_violation_record, update_violation_record,
)

router = APIRouter(tags=["violations"])


class ClearResult(BaseModel):
    deleted: int


@router.post(
    "/employees/{employee_id}/violations",
    response_model=ViolationRecordRead,
    status_code=status.HTTP_201_CREATED,
    summary="Assign a violation (core action — auto-computes offense number)",
)
def assign(
    db: DbSession, employee_id: Annotated[int, Path(ge=1)],
    payload: ViolationAssign, actor: ActorDep,
):
    return assign_violation(
        db, employee_id=employee_id, actor=actor, **payload.model_dump(exclude_unset=True),
    )


@router.get(
    "/employees/{employee_id}/violations",
    response_model=list[ViolationRecordRead],
)
def list_for_employee(
    db: DbSession,
    employee_id: Annotated[int, Path(ge=1)],
    page: PaginationDep,
    only_offense_number_gte: Annotated[int | None, Query(ge=1, description="Only 2nd+ offenses, 3rd+, etc.")] = None,
    since: Annotated[datetime | None, Query(description="Inclusive (UTC)")] = None,
    until: Annotated[datetime | None, Query(description="Inclusive (UTC)")] = None,
):
    return list_employee_violations(
        db, employee_id,
        only_offense_number_gte=only_offense_number_gte,
        since=since, until=until, limit=page.limit, offset=page.offset,
    )


@router.get(
    "/employees/{employee_id}/offense-summary",
    response_model=list[EmployeeOffenseSummaryRow],
    summary="Per-subsection offense breakdown (active + removed)",
)
def offense_summary(db: DbSession, employee_id: Annotated[int, Path(ge=1)]):
    return get_employee_offense_summary(db, employee_id)


@router.post(
    "/employees/{employee_id}/violations/clear",
    response_model=ClearResult,
    summary="Amnesty — remove all records for this employee, with audit log",
)
def clear_all(
    db: DbSession,
    employee_id: Annotated[int, Path(ge=1)],
    payload: ViolationRemovalCreate,
    actor: ActorDep,
):
    deleted = clear_employee_violations(
        db, employee_id, removed_by=actor, reason=payload.reason,
    )
    return ClearResult(deleted=deleted)



@router.get("/violations/recent", response_model=list[ViolationRecordFeedRead])
def recent(
    db: DbSession,
    days: Annotated[int, Query(ge=1, le=365)] = 30,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
):
    return list_recent_violations(db, days=days, limit=limit)


@router.get("/violations/{violation_id}", response_model=ViolationRecordRead)
def get_one(db: DbSession, violation_id: Annotated[int, Path(ge=1)]):
    record = get_violation_record(db, violation_id)
    if record is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"ViolationRecord {violation_id} not found")
    return record


@router.patch("/violations/{violation_id}", response_model=ViolationRecordRead)
def update(
    db: DbSession, violation_id: Annotated[int, Path(ge=1)],
    payload: ViolationRecordUpdate, actor: ActorDep,
):
    return update_violation_record(db, violation_id, **payload.model_dump(exclude_unset=True), actor=actor)


@router.post(
    "/violations/{violation_id}/remove",
    response_model=ViolationRemovalRead,
    status_code=status.HTTP_201_CREATED,
    summary="Remove one violation record, with audit log",
)
def remove_record(
    db: DbSession,
    violation_id: Annotated[int, Path(ge=1)],
    payload: ViolationRemovalCreate,
    actor: ActorDep,
):
    return remove_violation_record(
        db, violation_id, removed_by=actor, reason=payload.reason,
    )
