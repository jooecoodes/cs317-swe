from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Optional, Sequence
from zoneinfo import ZoneInfo

from sqlalchemy import String, case, delete, func, or_, select, update
from sqlalchemy.orm import Session, joinedload, selectinload

from models import ActivityEvent, Employee, EmployeeStatus, ViolationRecord, ViolationRemoval, ViolationType

import os

_LOG_TZ = ZoneInfo(os.getenv("LOG_TIMEZONE", "UTC"))

# ============================================================================
# ERRORS
# ============================================================================

class EmployeeNotFound(Exception):
    def __init__(self, employee_id: int):
        super().__init__(f"Employee {employee_id} not found")
        self.employee_id = employee_id


class ViolationTypeNotFound(Exception):
    def __init__(self, violation_type_id: int):
        super().__init__(f"ViolationType {violation_type_id} not found")
        self.violation_type_id = violation_type_id


class ViolationTypeInactive(Exception):
    def __init__(self, violation_type_id: int):
        super().__init__(f"ViolationType {violation_type_id} is inactive")
        self.violation_type_id = violation_type_id


class DuplicateEmployeeCode(Exception):
    def __init__(self, code: str):
        super().__init__(f"Employee code {code!r} already exists")
        self.code = code


class DuplicateViolationType(Exception):
    def __init__(self, name: str):
        super().__init__(f"ViolationType name {name!r} already exists")
        self.name = name


class ViolationRecordNotFound(Exception):
    def __init__(self, record_id: int):
        super().__init__(f"ViolationRecord {record_id} not found")
        self.record_id = record_id


class ViolationTypeInUse(Exception):
    def __init__(self, violation_type_id: int):
        super().__init__(
            f"ViolationType {violation_type_id} is referenced by existing records "
            f"and cannot be deleted; deactivate it instead."
        )
        self.violation_type_id = violation_type_id

# ---- HELPER FUNC ---------
def log_event(
    session: Session,
    *,
    actor: str,
    action: str,
    target_type: str,
    target_id: Optional[int] = None,
    employee_id: Optional[int] = None,
    summary: str,
    metadata: Optional[dict] = None,
) -> ActivityEvent:
    """Append an event to the audit log. Caller is responsible for commit."""
    now_utc = datetime.now(timezone.utc)
    event = ActivityEvent(
        occurred_at=now_utc,
        event_date=now_utc.astimezone(_LOG_TZ).date(),
        actor=actor.strip() or "unknown",
        action=action,
        target_type=target_type,
        target_id=target_id,
        employee_id=employee_id,
        summary=summary,
        metadata_json=metadata,
    )
    session.add(event)
    return event

# ============================================================================
# EMPLOYEE — WRITE (CRUD)
# ============================================================================



def create_employee(
    session: Session,
    *,
    employee_code: str,
    first_name: str,
    last_name: str,
    department: Optional[str] = None,
    position: Optional[str] = None,
    status: EmployeeStatus = EmployeeStatus.active,
    actor: str,
    commit: bool = True,
) -> Employee:
    exists = session.execute(
        select(Employee.id).where(Employee.employee_code == employee_code)
    ).scalar_one_or_none()
    if exists is not None:
        raise DuplicateEmployeeCode(employee_code)

    employee = Employee(
        employee_code=employee_code, first_name=first_name, last_name=last_name,
        department=department, position=position, status=status,
    )
    session.add(employee)
    session.flush()
    log_event(
        session, actor=actor, action="employee.created",
        target_type="employee", target_id=employee.id, employee_id=employee.id,
        summary=f"Added employee {employee.employee_code} ({employee.full_name})",
        metadata={"employee_code": employee.employee_code, "full_name": employee.full_name,
                  "department": employee.department, "position": employee.position},
    )
    if commit:
        session.commit()
    return employee

def create_employees_bulk(
    session: Session, rows: Sequence[dict], *, actor: str, commit: bool = True,
) -> list[Employee]:
    codes = [r["employee_code"] for r in rows]
    dupes = session.execute(
        select(Employee.employee_code).where(Employee.employee_code.in_(codes))
    ).scalars().all()
    if dupes:
        raise DuplicateEmployeeCode(dupes[0])

    employees = [Employee(**r) for r in rows]
    session.add_all(employees)
    session.flush()
    log_event(
        session, actor=actor, action="employees.bulk_created",
        target_type="employee",
        summary=f"Bulk-created {len(employees)} employees",
        metadata={"count": len(employees), "codes": [e.employee_code for e in employees]},
    )
    if commit:
        session.commit()
    return employees

def update_employee(
    session: Session,
    employee_id: int,
    *,
    first_name: Optional[str] = None,
    last_name: Optional[str] = None,
    department: Optional[str] = None,
    position: Optional[str] = None,
    employee_code: Optional[str] = None,
    actor: str,
    commit: bool = True,
) -> Employee:
    employee = session.get(Employee, employee_id)
    if employee is None:
        raise EmployeeNotFound(employee_id)

    changes: dict = {}
    if employee_code is not None and employee_code != employee.employee_code:
        clash = session.execute(
            select(Employee.id).where(
                Employee.employee_code == employee_code, Employee.id != employee_id
            )
        ).scalar_one_or_none()
        if clash is not None:
            raise DuplicateEmployeeCode(employee_code)
        changes["employee_code"] = employee_code
        employee.employee_code = employee_code
    if first_name is not None:
        changes["first_name"] = first_name
        employee.first_name = first_name
    if last_name is not None:
        changes["last_name"] = last_name
        employee.last_name = last_name
    if department is not None:
        changes["department"] = department
        employee.department = department
    if position is not None:
        changes["position"] = position
        employee.position = position

    if changes:
        log_event(
            session, actor=actor, action="employee.updated",
            target_type="employee", target_id=employee.id, employee_id=employee.id,
            summary=f"Updated {employee.employee_code}: {', '.join(changes)}",
            metadata={"changes": changes},
        )
    if commit:
        session.commit()
    return employee

def set_employee_status(
    session: Session, employee_id: int, status: EmployeeStatus, *, actor: str, commit: bool = True,
) -> Employee:
    employee = session.get(Employee, employee_id)
    if employee is None:
        raise EmployeeNotFound(employee_id)
    employee.status = status
    action = "employee.activated" if status == EmployeeStatus.active else "employee.deactivated"
    log_event(
        session, actor=actor, action=action,
        target_type="employee", target_id=employee.id, employee_id=employee.id,
        summary=f"{'Reactivated' if status == EmployeeStatus.active else 'Deactivated'} "
                f"{employee.employee_code} ({employee.full_name})",
        metadata={"new_status": status.value},
    )
    if commit:
        session.commit()
    return employee

def deactivate_employee(session: Session, employee_id: int, *, actor: str, commit: bool = True) -> Employee:
    """Soft delete — hides from default search but preserves history."""
    return set_employee_status(session, employee_id, EmployeeStatus.inactive, actor=actor, commit=commit)


def reactivate_employee(session: Session, employee_id: int, *, actor: str, commit: bool = True) -> Employee:
    return set_employee_status(session, employee_id, EmployeeStatus.active, actor=actor, commit=commit)

def delete_employee(session: Session, employee_id: int, *, actor: str, commit: bool = True) -> None:
    employee = session.get(Employee, employee_id)
    if employee is None:
        raise EmployeeNotFound(employee_id)
    log_event(
        session, actor=actor, action="employee.deleted",
        target_type="employee", target_id=employee.id, employee_id=employee.id,
        summary=f"Hard-deleted {employee.employee_code} ({employee.full_name})",
        metadata={"employee_code": employee.employee_code, "full_name": employee.full_name,
                  "violation_count": len(employee.violation_records)},
    )
    session.delete(employee)
    if commit:
        session.commit()

# ============================================================================
# EMPLOYEE — READ
# ============================================================================

def get_employee(session: Session, employee_id: int) -> Optional[Employee]:
    """Plain fetch, no relationships loaded."""
    return session.get(Employee, employee_id)


def get_employee_by_code(session: Session, employee_code: str) -> Optional[Employee]:
    return session.execute(
        select(Employee).where(Employee.employee_code == employee_code)
    ).scalar_one_or_none()


def search_employees(
    session: Session,
    search: Optional[str] = None,
    *,
    include_inactive: bool = False,
    department: Optional[str] = None,
    position: Optional[str] = None,
    min_points: Optional[int] = None,
    min_strikes: Optional[int] = None,
    limit: int = 25,
    offset: int = 0,
) -> Sequence:
    """
    Returns rows:
        id, employee_code, full_name, department, position,
        total_points, total_strikes
    Totals are computed in SQL — no child rows loaded. Filters on totals are
    also SQL-level (the hybrid expressions compile to correlated subqueries).
    """
    stmt = select(
        Employee.id,
        Employee.employee_code,
        Employee.full_name,
        Employee.department,
        Employee.position,
        Employee.status,
        Employee.total_points,
        Employee.total_strikes,
    )

    if search and (term := search.strip()):
        pattern = f"%{term}%"
        stmt = stmt.where(
            or_(
                Employee.first_name.ilike(pattern),
                Employee.last_name.ilike(pattern),
                Employee.employee_code.ilike(pattern),
                Employee.full_name.ilike(pattern),
            )
        )

    if department:
        stmt = stmt.where(Employee.department.ilike(f"%{department}%"))
    if position:
        stmt = stmt.where(Employee.position.ilike(f"%{position}%"))
    if not include_inactive:
        stmt = stmt.where(Employee.status == EmployeeStatus.active)
    if min_points is not None:
        stmt = stmt.where(Employee.total_points >= min_points)
    if min_strikes is not None:
        stmt = stmt.where(Employee.total_strikes >= min_strikes)

    stmt = (
        stmt.order_by(Employee.last_name, Employee.first_name, Employee.id)
        .limit(limit)
        .offset(offset)
    )
    return session.execute(stmt).all()


def count_employees(
    session: Session,
    *,
    include_inactive: bool = False,
    department: Optional[str] = None,
) -> int:
    """Total count for pagination footers."""
    stmt = select(func.count(Employee.id))
    if not include_inactive:
        stmt = stmt.where(Employee.status == EmployeeStatus.active)
    if department:
        stmt = stmt.where(Employee.department == department)
    return session.execute(stmt).scalar_one()


def get_employee_detail(session: Session, employee_id: int) -> Optional[Employee]:
    """
    Employee with `violation_records` eagerly loaded and each record's
    `violation_type` eagerly loaded. Totals come from hybrid properties.
    """
    stmt = (
        select(Employee)
        .options(
            selectinload(Employee.violation_records).joinedload(
                ViolationRecord.violation_type
            )
        )
        .where(Employee.id == employee_id)
    )
    return session.execute(stmt).scalar_one_or_none()


# ============================================================================
# VIOLATION TYPE — WRITE (CRUD)
# ============================================================================

def create_violation_type(
    session: Session, *, name: str, description: Optional[str] = None,
    default_points: int = 0, is_strike: bool = False, is_active: bool = True,
    actor: str, commit: bool = True,
) -> ViolationType:
    if default_points < 0:
        raise ValueError("default_points must be >= 0")
    exists = session.execute(select(ViolationType.id).where(ViolationType.name == name)).scalar_one_or_none()
    if exists is not None:
        raise DuplicateViolationType(name)
    vtype = ViolationType(name=name, description=description, default_points=default_points,
                          is_strike=is_strike, is_active=is_active)
    session.add(vtype)
    session.flush()
    log_event(
        session, actor=actor, action="violation_type.created",
        target_type="violation_type", target_id=vtype.id,
        summary=f"Added violation type '{vtype.name}' ({vtype.default_points} pts)",
        metadata={"name": vtype.name, "default_points": vtype.default_points, "is_strike": vtype.is_strike},
    )
    if commit:
        session.commit()
    return vtype

def update_violation_type(
    session: Session, violation_type_id: int, *,
    name: Optional[str] = None, description: Optional[str] = None,
    default_points: Optional[int] = None, is_strike: Optional[bool] = None,
    actor: str, commit: bool = True,
) -> ViolationType:
    vtype = session.get(ViolationType, violation_type_id)
    if vtype is None:
        raise ViolationTypeNotFound(violation_type_id)
    changes: dict = {}
    if name is not None and name != vtype.name:
        clash = session.execute(
            select(ViolationType.id).where(ViolationType.name == name, ViolationType.id != violation_type_id)
        ).scalar_one_or_none()
        if clash is not None:
            raise DuplicateViolationType(name)
        changes["name"] = name
        vtype.name = name
    if description is not None:
        changes["description"] = description
        vtype.description = description
    if default_points is not None:
        if default_points < 0:
            raise ValueError("default_points must be >= 0")
        changes["default_points"] = default_points
        vtype.default_points = default_points
    if is_strike is not None:
        changes["is_strike"] = is_strike
        vtype.is_strike = is_strike
    if changes:
        log_event(
            session, actor=actor, action="violation_type.updated",
            target_type="violation_type", target_id=vtype.id,
            summary=f"Updated violation type '{vtype.name}': {', '.join(changes)}",
            metadata={"changes": changes},
        )
    if commit:
        session.commit()
    return vtype

def set_violation_type_active(
    session: Session, violation_type_id: int, is_active: bool, *, actor: str, commit: bool = True,
) -> ViolationType:
    vtype = session.get(ViolationType, violation_type_id)
    if vtype is None:
        raise ViolationTypeNotFound(violation_type_id)
    vtype.is_active = is_active
    log_event(
        session, actor=actor,
        action="violation_type.activated" if is_active else "violation_type.deactivated",
        target_type="violation_type", target_id=vtype.id,
        summary=f"{'Activated' if is_active else 'Deactivated'} violation type '{vtype.name}'",
        metadata={"name": vtype.name},
    )
    if commit:
        session.commit()
    return vtype

def delete_violation_type(session: Session, violation_type_id: int, *, actor: str, commit: bool = True) -> None:
    vtype = session.get(ViolationType, violation_type_id)
    if vtype is None:
        raise ViolationTypeNotFound(violation_type_id)
    in_use = session.execute(
        select(func.count(ViolationRecord.id)).where(ViolationRecord.violation_type_id == violation_type_id)
    ).scalar_one()
    if in_use:
        raise ViolationTypeInUse(violation_type_id)
    log_event(
        session, actor=actor, action="violation_type.deleted",
        target_type="violation_type", target_id=vtype.id,
        summary=f"Deleted violation type '{vtype.name}'",
        metadata={"name": vtype.name},
    )
    session.delete(vtype)
    if commit:
        session.commit()

# ============================================================================
# VIOLATION TYPE — READ
# ============================================================================

def get_active_violation_types(session: Session) -> Sequence:
    """id, name, default_points, is_strike — for the dropdown."""
    stmt = (
        select(
            ViolationType.id,
            ViolationType.name,
            ViolationType.default_points,
            ViolationType.is_strike,
        )
        .where(ViolationType.is_active.is_(True))
        .order_by(ViolationType.name)
    )
    return session.execute(stmt).all()


def list_violation_types(
    session: Session,
    *,
    include_inactive: bool = True,
    only_strikes: Optional[bool] = None,
) -> Sequence[ViolationType]:
    """Full ORM rows, for admin screens."""
    stmt = select(ViolationType).order_by(ViolationType.name)
    if not include_inactive:
        stmt = stmt.where(ViolationType.is_active.is_(True))
    if only_strikes is True:
        stmt = stmt.where(ViolationType.is_strike.is_(True))
    elif only_strikes is False:
        stmt = stmt.where(ViolationType.is_strike.is_(False))
    return session.execute(stmt).scalars().all()


def get_violation_type(session: Session, violation_type_id: int) -> Optional[ViolationType]:
    return session.get(ViolationType, violation_type_id)


# ============================================================================
# VIOLATION RECORD — WRITE
# ============================================================================

def assign_violation(
    session: Session, *, employee_id: int, violation_type_id: int,
    notes: Optional[str] = None, issued_at: Optional[datetime] = None,
    issued_by: Optional[str] = None, actor: str, commit: bool = True,
) -> ViolationRecord:
    employee = session.get(Employee, employee_id)
    if employee is None:
        raise EmployeeNotFound(employee_id)
    vtype = session.get(ViolationType, violation_type_id)
    if vtype is None:
        raise ViolationTypeNotFound(violation_type_id)
    if not vtype.is_active:
        raise ViolationTypeInactive(violation_type_id)

    record = ViolationRecord(
        employee_id=employee.id, violation_type_id=vtype.id,
        issued_by=issued_by, issued_at=issued_at or datetime.now(timezone.utc),
        notes=notes, points=vtype.default_points, is_strike=vtype.is_strike,
    )
    session.add(record)
    session.flush()
    log_event(
        session, actor=actor, action="violation.assigned",
        target_type="violation", target_id=record.id, employee_id=record.employee_id,
        summary=f"Issued '{vtype.name}' ({record.points} pts"
                f"{', strike' if record.is_strike else ''}) to "
                f"{employee.employee_code} ({employee.full_name})",
        metadata={"violation_type_name": vtype.name, "points": record.points,
                  "is_strike": record.is_strike, "issued_by": issued_by,
                  "employee_code": employee.employee_code, "employee_full_name": employee.full_name},
    )

    if commit:
        session.commit()
    return record

def update_violation_record(
    session: Session, record_id: int, *,
    notes: Optional[str] = None, issued_by: Optional[str] = None,
    issued_at: Optional[datetime] = None, actor: str, commit: bool = True,
) -> ViolationRecord:
    record = session.get(ViolationRecord, record_id)
    if record is None:
        raise ViolationRecordNotFound(record_id)
    changes: dict = {}
    if notes is not None:
        changes["notes"] = notes
        record.notes = notes
    if issued_by is not None:
        changes["issued_by"] = issued_by
        record.issued_by = issued_by
    if issued_at is not None:
        changes["issued_at"] = issued_at.isoformat()
        record.issued_at = issued_at
    if changes:
        log_event(
            session, actor=actor, action="violation.updated",
            target_type="violation", target_id=record.id, employee_id=record.employee_id,
            summary=f"Updated violation #{record.id}: {', '.join(changes)}",
            metadata={"changes": changes},
        )
    if commit:
        session.commit()
    return record

def delete_violation_record(session: Session, record_id: int, *, commit: bool = True) -> None:
    record = session.get(ViolationRecord, record_id)
    if record is None:
        raise ViolationRecordNotFound(record_id)
    session.delete(record)
    if commit:
        session.commit()
    else:
        session.flush()

def clear_employee_violations(
    session: Session, employee_id: int, *, removed_by: str, reason: str, commit: bool = True,
) -> int:
    employee = session.get(Employee, employee_id)
    if employee is None:
        raise EmployeeNotFound(employee_id)
    records = session.execute(
        select(ViolationRecord)
        .options(joinedload(ViolationRecord.violation_type), joinedload(ViolationRecord.employee))
        .where(ViolationRecord.employee_id == employee_id)
    ).scalars().all()

    now = datetime.now(timezone.utc)
    for record in records:
        removal = ViolationRemoval(
            violation_record_id=record.id, violation_type_id=record.violation_type_id,
            violation_type_name=record.violation_type.name if record.violation_type else "",
            points=record.points, is_strike=record.is_strike,
            original_notes=record.notes, original_issued_by=record.issued_by,
            original_issued_at=record.issued_at,
            employee_id=record.employee_id,
            employee_code=employee.employee_code, employee_full_name=employee.full_name,
            removed_by=removed_by, reason=reason, removed_at=now,
        )
        session.add(removal)
        session.delete(record)
        log_event(
            session, actor=removed_by, action="violation.removed",
            target_type="violation", target_id=record.id, employee_id=employee.id,
            summary=f"Removed '{removal.violation_type_name}' from {employee.employee_code} "
                    f"({employee.full_name}) — amnesty — reason: {reason}",
            metadata={"violation_type_name": removal.violation_type_name, "points": removal.points,
                      "is_strike": removal.is_strike, "reason": reason, "amnesty": True,
                      "employee_code": employee.employee_code, "employee_full_name": employee.full_name},
        )

    if commit:
        session.commit()
    return len(records)

# ============================================================================
# VIOLATION RECORD — READ
# ============================================================================

def list_employee_violations(
    session: Session,
    employee_id: int,
    *,
    only_strikes: Optional[bool] = None,
    since: Optional[datetime] = None,
    until: Optional[datetime] = None,
    limit: int = 100,
    offset: int = 0,
) -> Sequence[ViolationRecord]:
    """Full ORM rows with violation_type eagerly loaded, newest first."""
    stmt = (
        select(ViolationRecord)
        .options(joinedload(ViolationRecord.violation_type))
        .where(ViolationRecord.employee_id == employee_id)
    )
    if only_strikes is True:
        stmt = stmt.where(ViolationRecord.is_strike.is_(True))
    elif only_strikes is False:
        stmt = stmt.where(ViolationRecord.is_strike.is_(False))
    if since is not None:
        stmt = stmt.where(ViolationRecord.issued_at >= since)
    if until is not None:
        stmt = stmt.where(ViolationRecord.issued_at <= until)

    stmt = stmt.order_by(ViolationRecord.issued_at.desc(), ViolationRecord.id.desc())
    stmt = stmt.limit(limit).offset(offset)
    return session.execute(stmt).scalars().all()


def list_recent_violations(
    session: Session,
    *,
    days: int = 30,
    only_strikes: bool = False,
    limit: int = 50,
) -> Sequence[ViolationRecord]:
    """Company-wide feed — "what happened in the last N days"."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    stmt = (
        select(ViolationRecord)
        .options(
            joinedload(ViolationRecord.violation_type),
            joinedload(ViolationRecord.employee),
        )
        .where(ViolationRecord.issued_at >= cutoff)
        .order_by(ViolationRecord.issued_at.desc())
        .limit(limit)
    )
    if only_strikes:
        stmt = stmt.where(ViolationRecord.is_strike.is_(True))
    return session.execute(stmt).scalars().all()


def get_violation_record(session: Session, record_id: int) -> Optional[ViolationRecord]:
    stmt = (
        select(ViolationRecord)
        .options(joinedload(ViolationRecord.violation_type))
        .where(ViolationRecord.id == record_id)
    )
    return session.execute(stmt).scalar_one_or_none()


# ============================================================================
# ANALYTICS / DASHBOARD
# ============================================================================

def get_employee_totals(session: Session, employee_id: int) -> dict:
    """Single-row totals for a specific employee, computed in SQL."""
    row = session.execute(
        select(
            Employee.id,
            Employee.total_points,
            Employee.total_strikes,
            func.count(ViolationRecord.id).label("total_records"),
        )
        .outerjoin(ViolationRecord, ViolationRecord.employee_id == Employee.id)
        .where(Employee.id == employee_id)
        .group_by(Employee.id)
    ).one_or_none()
    if row is None:
        raise EmployeeNotFound(employee_id)
    return {
        "employee_id": row.id,
        "total_points": row.total_points or 0,
        "total_strikes": row.total_strikes or 0,
        "total_records": row.total_records or 0,
    }


def top_offenders(
    session: Session,
    *,
    limit: int = 10,
    by: str = "points",   # "points" | "strikes" | "records"
) -> Sequence:
    """Leaderboard of employees by points, strikes, or record count."""
    order_col = {
        "points": Employee.total_points,
        "strikes": Employee.total_strikes,
        "records": (
            select(func.count(ViolationRecord.id))
            .where(ViolationRecord.employee_id == Employee.id)
            .correlate(Employee)
            .scalar_subquery()
        ),
    }.get(by)
    if order_col is None:
        raise ValueError("by must be 'points', 'strikes', or 'records'")

    stmt = (
        select(
            Employee.id,
            Employee.employee_code,
            Employee.full_name,
            Employee.department,
            Employee.total_points,
            Employee.total_strikes,
        )
        .where(Employee.status == EmployeeStatus.active)
        .order_by(order_col.desc(), Employee.id)
        .limit(limit)
    )
    return session.execute(stmt).all()


def department_summary(session: Session) -> Sequence:
    """Per-department counts and totals. Great for a dashboard chart."""
    stmt = (
        select(
            Employee.department.label("department"),
            func.count(func.distinct(Employee.id)).label("employees"),
            func.coalesce(func.sum(ViolationRecord.points), 0).label("total_points"),
            func.count(ViolationRecord.id).label("total_records"),
            func.coalesce(
                func.sum(func.cast(ViolationRecord.is_strike, type_=String)),
                "0",
            ).label("_tmp"),  # not used directly, see note below
        )
        .join(ViolationRecord, ViolationRecord.employee_id == Employee.id, isouter=True)
        .group_by(Employee.department)
        .order_by(func.coalesce(func.sum(ViolationRecord.points), 0).desc())
    )
    # The cast trick above is dialect-specific; do strikes via a separate
    # subquery count for portability:
    strike_counts = dict(
        session.execute(
            select(ViolationRecord.employee_id, func.count(ViolationRecord.id))
            .where(ViolationRecord.is_strike.is_(True))
            .group_by(ViolationRecord.employee_id)
        ).all()
    )
    emp_dept = dict(
        session.execute(select(Employee.id, Employee.department)).all()
    )
    rows = session.execute(stmt).all()
    out = []
    for r in rows:
        strikes_in_dept = sum(
            c for emp_id, c in strike_counts.items()
            if emp_dept.get(emp_id) == r.department
        )
        out.append({
            "department": r.department,
            "employees": r.employees,
            "total_points": r.total_points,
            "total_records": r.total_records,
            "total_strikes": strikes_in_dept,
        })
    return out


def violation_type_frequency(session: Session, *, limit: int = 20) -> Sequence:
    """How often each violation type gets issued. Rulebook usage report."""
    stmt = (
        select(
            ViolationType.id,
            ViolationType.name,
            ViolationType.default_points,
            ViolationType.is_strike,
            func.count(ViolationRecord.id).label("times_issued"),
            func.coalesce(func.sum(ViolationRecord.points), 0).label("total_points"),
        )
        .outerjoin(ViolationRecord, ViolationRecord.violation_type_id == ViolationType.id)
        .group_by(ViolationType.id)
        .order_by(func.count(ViolationRecord.id).desc())
        .limit(limit)
    )
    return session.execute(stmt).all()


def activity_over_time(
    session: Session,
    *,
    days: int = 30,
    bucket: str = "day",  # "day" | "week" | "month"
) -> Sequence:
    """
    Time series of violation counts. Uses SQLite's strftime for bucketing —
    swap to date_trunc for Postgres.
    """
    fmt = {
        "day": "%Y-%m-%d",
        "week": "%Y-W%W",
        "month": "%Y-%m",
    }.get(bucket)
    if fmt is None:
        raise ValueError("bucket must be 'day', 'week', or 'month'")

    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    stmt = (
        select(
            func.strftime(fmt, ViolationRecord.issued_at).label("bucket"),
            func.count(ViolationRecord.id).label("count"),
            func.coalesce(func.sum(ViolationRecord.points), 0).label("points"),
        )
        .where(ViolationRecord.issued_at >= cutoff)
        .group_by("bucket")
        .order_by("bucket")
    )
    return session.execute(stmt).all()


def employees_with_repeat_strikes(
    session: Session,
    *,
    min_strikes: int = 2,
) -> Sequence:
    """HR watchlist — employees at or above a strike threshold."""
    stmt = (
        select(
            Employee.id,
            Employee.employee_code,
            Employee.full_name,
            Employee.department,
            Employee.total_strikes,
            Employee.total_points,
        )
        .where(
            Employee.status == EmployeeStatus.active,
            Employee.total_strikes >= min_strikes,
        )
        .order_by(Employee.total_strikes.desc(), Employee.total_points.desc())
    )
    return session.execute(stmt).all()


def violation_free_employees(
    session: Session,
    *,
    since: Optional[datetime] = None,
) -> Sequence:
    """
    Employees with zero records. If `since` is given, means "clean since
    that date" — i.e., no records at or after it.
    """
    subq = select(ViolationRecord.employee_id)
    if since is not None:
        subq = subq.where(ViolationRecord.issued_at >= since)

    stmt = (
        select(
            Employee.id,
            Employee.employee_code,
            Employee.full_name,
            Employee.department,
        )
        .where(
            Employee.status == EmployeeStatus.active,
            Employee.id.not_in(subq),
        )
        .order_by(Employee.last_name, Employee.first_name)
    )
    return session.execute(stmt).all()



# ============================================================================
# VIOLATION REMOVAL — audit log
# ============================================================================

# use removed_by as the actor (no new param)
def remove_violation_record(
    session: Session, record_id: int, *, removed_by: str, reason: str, commit: bool = True,
) -> ViolationRemoval:
    record = session.execute(
        select(ViolationRecord)
        .options(joinedload(ViolationRecord.violation_type), joinedload(ViolationRecord.employee))
        .where(ViolationRecord.id == record_id)
    ).scalar_one_or_none()
    if record is None:
        raise ViolationRecordNotFound(record_id)

    removal = ViolationRemoval(
        violation_record_id=record.id, violation_type_id=record.violation_type_id,
        violation_type_name=record.violation_type.name if record.violation_type else "",
        points=record.points, is_strike=record.is_strike,
        original_notes=record.notes, original_issued_by=record.issued_by,
        original_issued_at=record.issued_at,
        employee_id=record.employee_id,
        employee_code=record.employee.employee_code if record.employee else "",
        employee_full_name=record.employee.full_name if record.employee else "",
        removed_by=removed_by, reason=reason, removed_at=datetime.now(timezone.utc),
    )
    session.add(removal)
    session.delete(record)
    session.flush()
    log_event(
        session, actor=removed_by, action="violation.removed",
        target_type="violation", target_id=record_id,
        employee_id=removal.employee_id,
        summary=f"Removed '{removal.violation_type_name}' from "
                f"{removal.employee_code} ({removal.employee_full_name}) — reason: {reason}",
        metadata={"violation_type_name": removal.violation_type_name, "points": removal.points,
                  "is_strike": removal.is_strike, "reason": reason,
                  "employee_code": removal.employee_code, "employee_full_name": removal.employee_full_name},
    )
    if commit:
        session.commit()
    return removal

def list_violation_removals(
    session: Session,
    *,
    employee_id: Optional[int] = None,
    removed_by: Optional[str] = None,
    since: Optional[datetime] = None,
    until: Optional[datetime] = None,
    search: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
) -> Sequence[ViolationRemoval]:
    stmt = (
        select(ViolationRemoval)
        .order_by(ViolationRemoval.removed_at.desc(), ViolationRemoval.id.desc())
    )
    if employee_id is not None:
        stmt = stmt.where(ViolationRemoval.employee_id == employee_id)
    if removed_by:
        stmt = stmt.where(ViolationRemoval.removed_by.ilike(f"%{removed_by}%"))
    if since is not None:
        stmt = stmt.where(ViolationRemoval.removed_at >= since)
    if until is not None:
        stmt = stmt.where(ViolationRemoval.removed_at <= until)
    if search and (term := search.strip()):
        pattern = f"%{term}%"
        stmt = stmt.where(or_(
            ViolationRemoval.reason.ilike(pattern),
            ViolationRemoval.employee_code.ilike(pattern),
            ViolationRemoval.employee_full_name.ilike(pattern),
            ViolationRemoval.violation_type_name.ilike(pattern),
        ))
    stmt = stmt.limit(limit).offset(offset)
    return session.execute(stmt).scalars().all()


def count_violation_removals(
    session: Session,
    *,
    employee_id: Optional[int] = None,
    removed_by: Optional[str] = None,
    since: Optional[datetime] = None,
    until: Optional[datetime] = None,
    search: Optional[str] = None,
) -> int:
    stmt = select(func.count(ViolationRemoval.id))
    if employee_id is not None:
        stmt = stmt.where(ViolationRemoval.employee_id == employee_id)
    if removed_by:
        stmt = stmt.where(ViolationRemoval.removed_by.ilike(f"%{removed_by}%"))
    if since is not None:
        stmt = stmt.where(ViolationRemoval.removed_at >= since)
    if until is not None:
        stmt = stmt.where(ViolationRemoval.removed_at <= until)
    if search and (term := search.strip()):
        pattern = f"%{term}%"
        stmt = stmt.where(or_(
            ViolationRemoval.reason.ilike(pattern),
            ViolationRemoval.employee_code.ilike(pattern),
            ViolationRemoval.employee_full_name.ilike(pattern),
            ViolationRemoval.violation_type_name.ilike(pattern),
        ))
    return session.execute(stmt).scalar_one()


def get_violation_removal(
    session: Session,
    removal_id: int,
) -> Optional[ViolationRemoval]:
    return session.get(ViolationRemoval, removal_id)


# ============================================================================
# ACTIVITY — read side
# ============================================================================

def list_activity_events(
    session: Session,
    *,
    day: Optional[date] = None,
    start: Optional[date] = None,
    end: Optional[date] = None,
    actor: Optional[str] = None,
    action: Optional[str] = None,
    target_type: Optional[str] = None,
    employee_id: Optional[int] = None,
    limit: int = 50,
    offset: int = 0,
) -> Sequence[ActivityEvent]:
    stmt = select(ActivityEvent).order_by(ActivityEvent.occurred_at.desc(), ActivityEvent.id.desc())
    if day is not None:
        stmt = stmt.where(ActivityEvent.event_date == day)
    if start is not None:
        stmt = stmt.where(ActivityEvent.event_date >= start)
    if end is not None:
        stmt = stmt.where(ActivityEvent.event_date <= end)
    if actor:
        stmt = stmt.where(ActivityEvent.actor.ilike(f"%{actor}%"))
    if action:
        stmt = stmt.where(ActivityEvent.action == action)
    if target_type:
        stmt = stmt.where(ActivityEvent.target_type == target_type)
    if employee_id is not None:
        stmt = stmt.where(ActivityEvent.employee_id == employee_id)
    return session.execute(stmt.limit(limit).offset(offset)).scalars().all()


def count_activity_events(
    session: Session,
    *,
    day: Optional[date] = None,
    start: Optional[date] = None,
    end: Optional[date] = None,
    actor: Optional[str] = None,
    action: Optional[str] = None,
    target_type: Optional[str] = None,
    employee_id: Optional[int] = None,
) -> int:
    stmt = select(func.count(ActivityEvent.id))
    if day is not None:
        stmt = stmt.where(ActivityEvent.event_date == day)
    if start is not None:
        stmt = stmt.where(ActivityEvent.event_date >= start)
    if end is not None:
        stmt = stmt.where(ActivityEvent.event_date <= end)
    if actor:
        stmt = stmt.where(ActivityEvent.actor.ilike(f"%{actor}%"))
    if action:
        stmt = stmt.where(ActivityEvent.action == action)
    if target_type:
        stmt = stmt.where(ActivityEvent.target_type == target_type)
    if employee_id is not None:
        stmt = stmt.where(ActivityEvent.employee_id == employee_id)
    return session.execute(stmt).scalar_one()


def get_activity_calendar(session: Session, *, start: date, end: date) -> Sequence:
    """Per-day rollup for the calendar UI. Returns one row per day with events."""
    total_stmt = (
        select(
            ActivityEvent.event_date,
            func.count(ActivityEvent.id).label("total"),
            func.sum(case((ActivityEvent.target_type == "employee", 1), else_=0)).label("employees"),
            func.sum(case((ActivityEvent.target_type == "violation", 1), else_=0)).label("violations"),
            func.sum(case((ActivityEvent.target_type == "violation_type", 1), else_=0)).label("violation_types"),
            func.sum(case((ActivityEvent.action == "violation.removed", 1), else_=0)).label("removals"),
        )
        .where(ActivityEvent.event_date >= start, ActivityEvent.event_date <= end)
        .group_by(ActivityEvent.event_date)
        .order_by(ActivityEvent.event_date)
    )
    return session.execute(total_stmt).all()


def get_daily_digest_events(session: Session, day: date) -> Sequence[ActivityEvent]:
    stmt = (
        select(ActivityEvent)
        .where(ActivityEvent.event_date == day)
        .order_by(ActivityEvent.occurred_at.asc(), ActivityEvent.id.asc())
    )
    return session.execute(stmt).scalars().all()
