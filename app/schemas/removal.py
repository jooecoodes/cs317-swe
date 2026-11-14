from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ViolationRemovalCreate(BaseModel):
    """Body for POST .../remove and POST .../clear.

    `removed_by` is sourced from the X-Actor header (ActorDep), not this body.
    Any `removed_by` key sent here → 422 (extra="forbid").
    """

    model_config = ConfigDict(extra="forbid")

    reason: str = Field(
        min_length=1,
        max_length=2000,
        description="Why this violation is being removed",
    )


class ViolationRemovalRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    violation_record_id: int
    subsection_id: int | None = None
    subsection_name: str
    violation_type_name: str
    offense_number: int
    penalty_description: str | None = None
    original_notes: str | None = None
    original_issued_by: str | None = None
    original_issued_at: datetime

    employee_id: int
    employee_code: str
    employee_full_name: str

    removed_by: str
    reason: str
    removed_at: datetime
