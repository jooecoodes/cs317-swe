from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional, Sequence

from sqlalchemy import String, delete, func, or_, select, update
from sqlalchemy.orm import Session, joinedload, selectinload

from models import Employee, EmployeeStatus, ViolationRecord, ViolationType


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
    commit: bool = True,
) -> Employee:
    """
    Insert a new employee. Raises DuplicateEmployeeCode if the code is taken.
    """
    exists = session.execute(
        select(Employee.id).where(Employee.employee_code == employee_code)
    ).scalar_one_or_none()
    if exists is not None:
        raise DuplicateEmployeeCode(employee_code)

    employee = Employee(
        employee_code=employee_code,
        first_name=first_name,
        last_name=last_name,
        department=department,
        position=position,
        status=status,
    )
    session.add(employee)
    if commit:
        session.commit()
    else:
        session.flush()
    return employee


def create_employees_bulk(
    session: Session,
    rows: Sequence[dict],
    *,
    commit: bool = True,
) -> list[Employee]:
    """
    Insert many employees in one transaction. Each dict must contain the same
    keys as create_employee's kwargs (minus commit).
    """
    codes = [r["employee_code"] for r in rows]
    dupes = session.execute(
        select(Employee.employee_code).where(Employee.employee_code.in_(codes))
    ).scalars().all()
    if dupes:
        raise DuplicateEmployeeCode(dupes[0])

    employees = [Employee(**r) for r in rows]
    session.add_all(employees)
    if commit:
        session.commit()
    else:
        session.flush()
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
    commit: bool = True,
) -> Employee:
    """Partial update. Only non-None fields are applied."""
    employee = session.get(Employee, employee_id)
    if employee is None:
        raise EmployeeNotFound(employee_id)

    if employee_code is not None and employee_code != employee.employee_code:
        clash = session.execute(
            select(Employee.id).where(
                Employee.employee_code == employee_code,
                Employee.id != employee_id,
            )
        ).scalar_one_or_none()
        if clash is not None:
            raise DuplicateEmployeeCode(employee_code)
        employee.employee_code = employee_code

    if first_name is not None:
        employee.first_name = first_name
    if last_name is not None:
        employee.last_name = last_name
    if department is not None:
        employee.department = department
    if position is not None:
        employee.position = position

    if commit:
        session.commit()
    else:
        session.flush()
    return employee


def set_employee_status(
    session: Session,
    employee_id: int,
    status: EmployeeStatus,
    *,
    commit: bool = True,
) -> Employee:
    employee = session.get(Employee, employee_id)
    if employee is None:
        raise EmployeeNotFound(employee_id)
    employee.status = status
    if commit:
        session.commit()
    else:
        session.flush()
    return employee


def deactivate_employee(session: Session, employee_id: int, *, commit: bool = True) -> Employee:
    """Soft delete — hides from default search but preserves history."""
    return set_employee_status(session, employee_id, EmployeeStatus.inactive, commit=commit)


def reactivate_employee(session: Session, employee_id: int, *, commit: bool = True) -> Employee:
    return set_employee_status(session, employee_id, EmployeeStatus.active, commit=commit)


def delete_employee(session: Session, employee_id: int, *, commit: bool = True) -> None:
    """
    Hard delete. Cascades to violation_records (see ondelete=CASCADE on FK).
    Prefer deactivate_employee for real HR use.
    """
    employee = session.get(Employee, employee_id)
    if employee is None:
        raise EmployeeNotFound(employee_id)
    session.delete(employee)
    if commit:
        session.commit()
    else:
        session.flush()


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
    session: Session,
    *,
    name: str,
    description: Optional[str] = None,
    default_points: int = 0,
    is_strike: bool = False,
    is_active: bool = True,
    commit: bool = True,
) -> ViolationType:
    if default_points < 0:
        raise ValueError("default_points must be >= 0")

    exists = session.execute(
        select(ViolationType.id).where(ViolationType.name == name)
    ).scalar_one_or_none()
    if exists is not None:
        raise DuplicateViolationType(name)

    vtype = ViolationType(
        name=name,
        description=description,
        default_points=default_points,
        is_strike=is_strike,
        is_active=is_active,
    )
    session.add(vtype)
    if commit:
        session.commit()
    else:
        session.flush()
    return vtype


def update_violation_type(
    session: Session,
    violation_type_id: int,
    *,
    name: Optional[str] = None,
    description: Optional[str] = None,
    default_points: Optional[int] = None,
    is_strike: Optional[bool] = None,
    commit: bool = True,
) -> ViolationType:
    """
    Partial update. NOTE: editing default_points/is_strike does NOT rewrite
    historical records — they keep their snapshotted values (that's the point).
    """
    vtype = session.get(ViolationType, violation_type_id)
    if vtype is None:
        raise ViolationTypeNotFound(violation_type_id)

    if name is not None and name != vtype.name:
        clash = session.execute(
            select(ViolationType.id).where(
                ViolationType.name == name,
                ViolationType.id != violation_type_id,
            )
        ).scalar_one_or_none()
        if clash is not None:
            raise DuplicateViolationType(name)
        vtype.name = name

    if description is not None:
        vtype.description = description
    if default_points is not None:
        if default_points < 0:
            raise ValueError("default_points must be >= 0")
        vtype.default_points = default_points
    if is_strike is not None:
        vtype.is_strike = is_strike

    if commit:
        session.commit()
    else:
        session.flush()
    return vtype


def set_violation_type_active(
    session: Session,
    violation_type_id: int,
    is_active: bool,
    *,
    commit: bool = True,
) -> ViolationType:
    vtype = session.get(ViolationType, violation_type_id)
    if vtype is None:
        raise ViolationTypeNotFound(violation_type_id)
    vtype.is_active = is_active
    if commit:
        session.commit()
    else:
        session.flush()
    return vtype


def delete_violation_type(session: Session, violation_type_id: int, *, commit: bool = True) -> None:
    """
    Hard delete only allowed when no violation_records reference it.
    Otherwise raise ViolationTypeInUse (use set_violation_type_active(False)).
    """
    vtype = session.get(ViolationType, violation_type_id)
    if vtype is None:
        raise ViolationTypeNotFound(violation_type_id)

    in_use = session.execute(
        select(func.count(ViolationRecord.id)).where(
            ViolationRecord.violation_type_id == violation_type_id
        )
    ).scalar_one()
    if in_use:
        raise ViolationTypeInUse(violation_type_id)

    session.delete(vtype)
    if commit:
        session.commit()
    else:
        session.flush()


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
    session: Session,
    *,
    employee_id: int,
    violation_type_id: int,
    notes: Optional[str] = None,
    issued_at: Optional[datetime] = None,
    issued_by: Optional[str] = None,
    commit: bool = True,
) -> ViolationRecord:
    """
    Validates employee + violation type, inserts a record with
    points/is_strike snapshotted from the type.
    """
    employee = session.get(Employee, employee_id)
    if employee is None:
        raise EmployeeNotFound(employee_id)

    vtype = session.get(ViolationType, violation_type_id)
    if vtype is None:
        raise ViolationTypeNotFound(violation_type_id)
    if not vtype.is_active:
        raise ViolationTypeInactive(violation_type_id)

    record = ViolationRecord(
        employee_id=employee.id,
        violation_type_id=vtype.id,
        issued_by=issued_by,
        issued_at=issued_at or datetime.now(timezone.utc),
        notes=notes,
        points=vtype.default_points,
        is_strike=vtype.is_strike,
    )
    session.add(record)
    if commit:
        session.commit()
    else:
        session.flush()
    return record


def update_violation_record(
    session: Session,
    record_id: int,
    *,
    notes: Optional[str] = None,
    issued_by: Optional[str] = None,
    issued_at: Optional[datetime] = None,
    commit: bool = True,
) -> ViolationRecord:
    """
    Partial update of a record's metadata.
    points / is_strike / violation_type_id are intentionally NOT editable —
    they're the historical snapshot. To "fix" one, delete and re-issue.
    """
    record = session.get(ViolationRecord, record_id)
    if record is None:
        raise ViolationRecordNotFound(record_id)

    if notes is not None:
        record.notes = notes
    if issued_by is not None:
        record.issued_by = issued_by
    if issued_at is not None:
        record.issued_at = issued_at

    if commit:
        session.commit()
    else:
        session.flush()
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


def clear_employee_violations(session: Session, employee_id: int, *, commit: bool = True) -> int:
    """
    Delete every violation record for an employee (e.g., annual amnesty).
    Returns the number of rows deleted.
    """
    employee = session.get(Employee, employee_id)
    if employee is None:
        raise EmployeeNotFound(employee_id)
    result = session.execute(
        delete(ViolationRecord).where(ViolationRecord.employee_id == employee_id)
    )
    if commit:
        session.commit()
    else:
        session.flush()
    return result.rowcount or 0


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
