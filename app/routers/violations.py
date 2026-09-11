from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from pydantic import BaseModel

from app.deps import DbSession, PaginationDep, require_admin
from app.schemas.violation import (
    ViolationAssign,
    ViolationRecordFeedRead,
    ViolationRecordRead,
    ViolationRecordUpdate,
)
from queries import (
    assign_violation,
    clear_employee_violations,
    delete_violation_record,
    get_violation_record,
    list_employee_violations,
    list_recent_violations,
    update_violation_record,
)

router = APIRouter(tags=["violations"])


class ClearResult(BaseModel):
    deleted: int


# ============ nested under an employee ============

@router.post(
    "/employees/{employee_id}/violations",
    response_model=ViolationRecordRead,
    status_code=status.HTTP_201_CREATED,
    summary="Assign a violation (core action)",
)
def assign(
    db: DbSession,
    employee_id: Annotated[int, Path(ge=1)],
    payload: ViolationAssign,
):
    return assign_violation(db, employee_id=employee_id, **payload.model_dump(exclude_unset=True))


@router.get(
    "/employees/{employee_id}/violations",
    response_model=list[ViolationRecordRead],
)
def list_for_employee(
    db: DbSession,
    employee_id: Annotated[int, Path(ge=1)],
    page: PaginationDep,
    only_strikes: Annotated[bool | None, Query()] = None,
    since: Annotated[datetime | None, Query(description="Inclusive (UTC)")] = None,
    until: Annotated[datetime | None, Query(description="Inclusive (UTC)")] = None,
):
    return list_employee_violations(
        db,
        employee_id,
        only_strikes=only_strikes,
        since=since,
        until=until,
        limit=page.limit,
        offset=page.offset,
    )


@router.delete(
    "/employees/{employee_id}/violations",
    response_model=ClearResult,
    dependencies=[Depends(require_admin)],
    summary="Amnesty — wipe all records for this employee",
)
def clear_all(db: DbSession, employee_id: Annotated[int, Path(ge=1)]):
    deleted = clear_employee_violations(db, employee_id)
    return ClearResult(deleted=deleted)


# ============ company-wide ============
# /violations/recent BEFORE /violations/{id}

@router.get(
    "/violations/recent",
    response_model=list[ViolationRecordFeedRead],
    summary="Recent company-wide feed",
)
def recent(
    db: DbSession,
    days: Annotated[int, Query(ge=1, le=365)] = 30,
    only_strikes: Annotated[bool, Query()] = False,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
):
    return list_recent_violations(db, days=days, only_strikes=only_strikes, limit=limit)


@router.get("/violations/{violation_id}", response_model=ViolationRecordRead)
def get_one(db: DbSession, violation_id: Annotated[int, Path(ge=1)]):
    record = get_violation_record(db, violation_id)
    if record is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"ViolationRecord {violation_id} not found")
    return record


@router.patch("/violations/{violation_id}", response_model=ViolationRecordRead)
def update(
    db: DbSession,
    violation_id: Annotated[int, Path(ge=1)],
    payload: ViolationRecordUpdate,
):
    return update_violation_record(db, violation_id, **payload.model_dump(exclude_unset=True))


@router.delete(
    "/violations/{violation_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_admin)],
)
def remove(db: DbSession, violation_id: Annotated[int, Path(ge=1)]):
    delete_violation_record(db, violation_id)
