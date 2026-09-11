from __future__ import annotations

import enum
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Enum as SAEnum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
    false,
    select,
    true,
)
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    mapped_column,
    relationship,
)


class Base(DeclarativeBase):
    pass


class EmployeeStatus(str, enum.Enum):
    active = "active"
    inactive = "inactive"


class Employee(Base):
    __tablename__ = "employees"

    id: Mapped[int] = mapped_column(primary_key=True)

    employee_code: Mapped[str] = mapped_column(
        String(50), unique=True, index=True, nullable=False
    )
    first_name: Mapped[str] = mapped_column(String(100), nullable=False)
    last_name: Mapped[str] = mapped_column(String(100), nullable=False)

    department: Mapped[Optional[str]] = mapped_column(String(100))
    position: Mapped[Optional[str]] = mapped_column(String(100))

    status: Mapped[EmployeeStatus] = mapped_column(
        SAEnum(EmployeeStatus, name="employee_status", native_enum=False, length=20),
        default=EmployeeStatus.active,
        server_default=EmployeeStatus.active.value,
        nullable=False,
        index=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    violation_records: Mapped[list["ViolationRecord"]] = relationship(
        back_populates="employee",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="ViolationRecord.issued_at.desc()",
    )

    __table_args__ = (
        Index("ix_employees_last_first", "last_name", "first_name"),
    )

    # ---- derived attributes -------------------------------------------------

    @hybrid_property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}"

    @full_name.inplace.expression
    @classmethod
    def _full_name_expr(cls):
        # SQLAlchemy renders `+` as || / concat depending on dialect
        return cls.first_name + " " + cls.last_name

    @hybrid_property
    def total_points(self) -> int:
        return sum(r.points for r in self.violation_records)

    @total_points.inplace.expression
    @classmethod
    def _total_points_expr(cls):
        return (
            select(func.coalesce(func.sum(ViolationRecord.points), 0))
            .where(ViolationRecord.employee_id == cls.id)
            .correlate(cls)
            .scalar_subquery()
        )

    @hybrid_property
    def total_strikes(self) -> int:
        return sum(1 for r in self.violation_records if r.is_strike)

    @total_strikes.inplace.expression
    @classmethod
    def _total_strikes_expr(cls):
        return (
            select(func.count(ViolationRecord.id))
            .where(
                ViolationRecord.employee_id == cls.id,
                ViolationRecord.is_strike.is_(True),
            )
            .correlate(cls)
            .scalar_subquery()
        )


class ViolationType(Base):
    __tablename__ = "violation_types"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)

    default_points: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    is_strike: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=false()
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=true(), index=True
    )

    violation_records: Mapped[list["ViolationRecord"]] = relationship(
        back_populates="violation_type"
    )

    __table_args__ = (
        CheckConstraint(
            "default_points >= 0",
            name="ck_violation_types_default_points_non_negative",
        ),
    )


class ViolationRecord(Base):
    """A single issued violation. A strike is simply is_strike == True."""

    __tablename__ = "violation_records"

    id: Mapped[int] = mapped_column(primary_key=True)

    employee_id: Mapped[int] = mapped_column(
        ForeignKey("employees.id", ondelete="CASCADE"), nullable=False, index=True
    )
    violation_type_id: Mapped[int] = mapped_column(
        ForeignKey("violation_types.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    issued_by: Mapped[Optional[str]] = mapped_column(String(150))
    issued_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), index=True
    )
    notes: Mapped[Optional[str]] = mapped_column(Text)

    # Snapshots — copied from the violation type at issue time.
    points: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_strike: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, index=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    employee: Mapped["Employee"] = relationship(back_populates="violation_records")
    violation_type: Mapped["ViolationType"] = relationship(
        back_populates="violation_records"
    )

    __table_args__ = (
        CheckConstraint("points >= 0", name="ck_violation_records_points_non_negative"),
        Index("ix_violation_records_employee_issued_at", "employee_id", "issued_at"),
    )
