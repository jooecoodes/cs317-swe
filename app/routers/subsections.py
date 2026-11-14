from typing import Annotated

from fastapi import APIRouter, HTTPException, Path, Query, status

from app.deps import ActorDep, DbSession
from app.schemas.violation import (
    PenaltyReplaceBody, SubsectionCreate, SubsectionOption,
    SubsectionRead, SubsectionUpdate,
)
from queries import (
    create_subsection, delete_subsection, get_subsection, list_subsections,
    replace_penalties, set_subsection_active, update_subsection,
)

router = APIRouter(tags=["subsections"])


# ---- nested under a violation type ----

@router.get(
    "/violation-types/{violation_type_id}/subsections",
    response_model=list[SubsectionOption],
    summary="Active subsections of a violation type (cascading picker)",
)
def list_for_type(
    db: DbSession,
    violation_type_id: Annotated[int, Path(ge=1)],
    include_inactive: Annotated[bool, Query()] = False,
):
    return list_subsections(db, violation_type_id, include_inactive=include_inactive)


@router.post(
    "/violation-types/{violation_type_id}/subsections",
    response_model=SubsectionRead,
    status_code=status.HTTP_201_CREATED,
)
def create(
    db: DbSession, violation_type_id: Annotated[int, Path(ge=1)],
    payload: SubsectionCreate, actor: ActorDep,
):
    return create_subsection(
        db, violation_type_id=violation_type_id, **payload.model_dump(), actor=actor,
    )


# ---- direct subsection access ----

@router.get("/subsections/{subsection_id}", response_model=SubsectionRead, summary="Subsection with penalties")
def get_one(db: DbSession, subsection_id: Annotated[int, Path(ge=1)]):
    sub = get_subsection(db, subsection_id)
    if sub is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"ViolationSubsection {subsection_id} not found")
    return sub


@router.patch("/subsections/{subsection_id}", response_model=SubsectionRead)
def update(
    db: DbSession, subsection_id: Annotated[int, Path(ge=1)],
    payload: SubsectionUpdate, actor: ActorDep,
):
    return update_subsection(db, subsection_id, **payload.model_dump(exclude_unset=True), actor=actor)


@router.post("/subsections/{subsection_id}/activate", response_model=SubsectionRead)
def activate(db: DbSession, subsection_id: Annotated[int, Path(ge=1)], actor: ActorDep):
    return set_subsection_active(db, subsection_id, True, actor=actor)


@router.post("/subsections/{subsection_id}/deactivate", response_model=SubsectionRead)
def deactivate(db: DbSession, subsection_id: Annotated[int, Path(ge=1)], actor: ActorDep):
    return set_subsection_active(db, subsection_id, False, actor=actor)


@router.delete("/subsections/{subsection_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove(db: DbSession, subsection_id: Annotated[int, Path(ge=1)], actor: ActorDep):
    delete_subsection(db, subsection_id, actor=actor)


# ---- penalties ----

@router.put(
    "/subsections/{subsection_id}/penalties",
    response_model=SubsectionRead,
    summary="Replace all penalty tiers for a subsection",
)
def set_penalties(
    db: DbSession, subsection_id: Annotated[int, Path(ge=1)],
    payload: PenaltyReplaceBody, actor: ActorDep,
):
    return replace_penalties(
        db, subsection_id,
        [p.model_dump() for p in payload.penalties],
        actor=actor,
    )
