from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status

from app.deps import DbSession, require_admin
from app.schemas.violation import (
    ViolationTypeCreate,
    ViolationTypeOption,
    ViolationTypeRead,
    ViolationTypeUpdate,
)
from queries import (
    create_violation_type,
    delete_violation_type,
    get_active_violation_types,
    get_violation_type,
    list_violation_types,
    set_violation_type_active,
    update_violation_type,
)

router = APIRouter(prefix="/violation-types", tags=["violation-types"])


@router.get("", response_model=list[ViolationTypeOption], summary="Active types (dropdown)")
def active(db: DbSession):
    return get_active_violation_types(db)


@router.get("/all", response_model=list[ViolationTypeRead], summary="All types (admin view)")
def list_all(
    db: DbSession,
    include_inactive: Annotated[bool, Query()] = True,
    only_strikes: Annotated[bool | None, Query(description="None=all, true=only strikes, false=only non-strikes")] = None,
):
    return list_violation_types(db, include_inactive=include_inactive, only_strikes=only_strikes)


@router.get("/{violation_type_id}", response_model=ViolationTypeRead)
def get_one(db: DbSession, violation_type_id: Annotated[int, Path(ge=1)]):
    vtype = get_violation_type(db, violation_type_id)
    if vtype is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"ViolationType {violation_type_id} not found")
    return vtype


@router.post(
    "",
    response_model=ViolationTypeRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_admin)],
)
def create(db: DbSession, payload: ViolationTypeCreate):
    return create_violation_type(db, **payload.model_dump())


@router.patch(
    "/{violation_type_id}",
    response_model=ViolationTypeRead,
    dependencies=[Depends(require_admin)],
)
def update(
    db: DbSession,
    violation_type_id: Annotated[int, Path(ge=1)],
    payload: ViolationTypeUpdate,
):
    return update_violation_type(db, violation_type_id, **payload.model_dump(exclude_unset=True))


@router.post(
    "/{violation_type_id}/activate",
    response_model=ViolationTypeRead,
    dependencies=[Depends(require_admin)],
)
def activate(db: DbSession, violation_type_id: Annotated[int, Path(ge=1)]):
    return set_violation_type_active(db, violation_type_id, True)


@router.post(
    "/{violation_type_id}/deactivate",
    response_model=ViolationTypeRead,
    dependencies=[Depends(require_admin)],
)
def deactivate(db: DbSession, violation_type_id: Annotated[int, Path(ge=1)]):
    return set_violation_type_active(db, violation_type_id, False)


@router.delete(
    "/{violation_type_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_admin)],
)
def remove(db: DbSession, violation_type_id: Annotated[int, Path(ge=1)]):
    delete_violation_type(db, violation_type_id)
