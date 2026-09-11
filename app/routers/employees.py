from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status

from app.deps import DbSession, PaginationDep, require_admin
from app.schemas.common import Page
from app.schemas.employee import (
    BulkCreateResult,
    EmployeeCreate,
    EmployeeDetail,
    EmployeeRead,
    EmployeeSummary,
    EmployeeTotals,
    EmployeeUpdate,
)
from queries import (
    count_employees,
    create_employee,
    create_employees_bulk,
    deactivate_employee,
    delete_employee,
    get_employee_by_code,
    get_employee_detail,
    get_employee_totals,
    reactivate_employee,
    search_employees,
    update_employee,
)

router = APIRouter(prefix="/employees", tags=["employees"])


@router.get("", response_model=Page[EmployeeSummary], summary="Search employees")
def list_employees(
    db: DbSession,
    page: PaginationDep,
    search: Annotated[str | None, Query(max_length=100)] = None,
    department: Annotated[str | None, Query(max_length=100)] = None,
    position: Annotated[str | None, Query(max_length=100)] = None,
    min_points: Annotated[int | None, Query(ge=0)] = None,
    min_strikes: Annotated[int | None, Query(ge=0)] = None,
    include_inactive: Annotated[bool, Query()] = False,
):
    items = search_employees(
        db,
        search=search,
        include_inactive=include_inactive,
        department=department,
        position=position,
        min_points=min_points,
        min_strikes=min_strikes,
        limit=page.limit,
        offset=page.offset,
    )
    # count_employees only accepts department + include_inactive (DB dev's code).
    total = count_employees(db, include_inactive=include_inactive, department=department)
    return Page(items=items, total=total, limit=page.limit, offset=page.offset)


@router.get("/by-code/{code}", response_model=EmployeeRead, summary="Look up by employee code")
def get_by_code(db: DbSession, code: Annotated[str, Path(min_length=1, max_length=50)]):
    employee = get_employee_by_code(db, code)
    if employee is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Employee code {code!r} not found")
    return employee


@router.get("/{employee_id}/totals", response_model=EmployeeTotals, summary="Cheap totals")
def totals(db: DbSession, employee_id: Annotated[int, Path(ge=1)]):
    return get_employee_totals(db, employee_id)  # raises EmployeeNotFound


@router.get("/{employee_id}", response_model=EmployeeDetail, summary="Full profile + history")
def detail(db: DbSession, employee_id: Annotated[int, Path(ge=1)]):
    employee = get_employee_detail(db, employee_id)
    if employee is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Employee {employee_id} not found")
    return employee


@router.post("", response_model=EmployeeRead, status_code=status.HTTP_201_CREATED)
def create(db: DbSession, payload: EmployeeCreate):
    return create_employee(db, **payload.model_dump())


@router.post("/bulk", response_model=BulkCreateResult, status_code=status.HTTP_201_CREATED)
def bulk_create(db: DbSession, payload: list[EmployeeCreate]):
    created = create_employees_bulk(db, [e.model_dump() for e in payload])
    return BulkCreateResult(created=len(created), employees=created)


@router.patch("/{employee_id}", response_model=EmployeeRead)
def update(
    db: DbSession,
    employee_id: Annotated[int, Path(ge=1)],
    payload: EmployeeUpdate,
):
    return update_employee(db, employee_id, **payload.model_dump(exclude_unset=True))


@router.post("/{employee_id}/deactivate", response_model=EmployeeRead)
def deactivate(db: DbSession, employee_id: Annotated[int, Path(ge=1)]):
    return deactivate_employee(db, employee_id)


@router.post("/{employee_id}/reactivate", response_model=EmployeeRead)
def reactivate(db: DbSession, employee_id: Annotated[int, Path(ge=1)]):
    return reactivate_employee(db, employee_id)


@router.delete(
    "/{employee_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_admin)],
)
def hard_delete(db: DbSession, employee_id: Annotated[int, Path(ge=1)]):
    delete_employee(db, employee_id)
