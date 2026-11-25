from __future__ import annotations

import os
from datetime import date, datetime, timedelta, timezone
from typing import Optional, Sequence
from zoneinfo import ZoneInfo

from sqlalchemy import (
    String, Text, DateTime,       # ← add these
    case, cast, delete, func, literal, null, or_, select, union_all,
)
from sqlalchemy.orm import Session, joinedload, selectinload

from models import (
    ActivityEvent,
    Employee,
    EmployeeStatus,
    EmployeeType,
    Penalty,
    ViolationRecord,
    ViolationRemoval,
    ViolationSubsection,
    ViolationType,
)


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


class DuplicateViolationType(Exception):
    def __init__(self, name: str):
        super().__init__(f"ViolationType name {name!r} already exists")
        self.name = name


class ViolationTypeInUse(Exception):
    def __init__(self, violation_type_id: int):
        super().__init__(
            f"ViolationType {violation_type_id} has issued violations and cannot be deleted; "
            f"deactivate it instead."
        )
        self.violation_type_id = violation_type_id


class SubsectionNotFound(Exception):
    def __init__(self, subsection_id: int):
        super().__init__(f"ViolationSubsection {subsection_id} not found")
        self.subsection_id = subsection_id


class SubsectionInactive(Exception):
    def __init__(self, subsection_id: int):
        super().__init__(f"ViolationSubsection {subsection_id} is inactive")
        self.subsection_id = subsection_id


class DuplicateSubsection(Exception):
    def __init__(self, violation_type_id: int, name: str):
        super().__init__(f"Subsection {name!r} already exists under this violation type")
        self.violation_type_id = violation_type_id
        self.name = name


class SubsectionInUse(Exception):
    def __init__(self, subsection_id: int):
        super().__init__(
            f"ViolationSubsection {subsection_id} has issued violations and cannot be deleted; "
            f"deactivate it instead."
        )
        self.subsection_id = subsection_id


class NoPenaltyDefined(Exception):
    def __init__(self, subsection_id: int, offense_number: int):
        super().__init__(
            f"No penalty defined for ViolationSubsection {subsection_id} at "
            f"offense #{offense_number}. Add a penalty tier first."
        )
        self.subsection_id = subsection_id
        self.offense_number = offense_number


class DuplicateEmployeeCode(Exception):
    def __init__(self, code: str):
        super().__init__(f"Employee code {code!r} already exists")
        self.code = code


class ViolationRecordNotFound(Exception):
    def __init__(self, record_id: int):
        super().__init__(f"ViolationRecord {record_id} not found")
        self.record_id = record_id


# ============================================================================
# ACTIVITY LOGGING
# ============================================================================

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
# EMPLOYEE — WRITE
# ============================================================================

def create_employee(
    session: Session, *, employee_code: str, first_name: str, last_name: str,
    department: Optional[str] = None, position: Optional[str] = None,
    employee_type: EmployeeType = EmployeeType.employee,
    status: EmployeeStatus = EmployeeStatus.active, actor: str, commit: bool = True,
) -> Employee:
    if session.execute(
        select(Employee.id).where(Employee.employee_code == employee_code)
    ).scalar_one_or_none() is not None:
        raise DuplicateEmployeeCode(employee_code)
    employee = Employee(
        employee_code=employee_code, first_name=first_name, last_name=last_name,
        department=department, position=position, employee_type=employee_type,
        status=status,
    )
    session.add(employee)
    session.flush()
    log_event(
        session, actor=actor, action="employee.created",
        target_type="employee", target_id=employee.id, employee_id=employee.id,
        summary=f"Added employee {employee.employee_code} ({employee.full_name})",
        metadata={"employee_code": employee.employee_code, "full_name": employee.full_name,
                  "department": employee.department, "position": employee.position,
                  "employee_type": employee.employee_type.value},
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
    session: Session, employee_id: int, *,
    first_name: Optional[str] = None, last_name: Optional[str] = None,
    department: Optional[str] = None, position: Optional[str] = None,
    employee_type: Optional[EmployeeType] = None,
    employee_code: Optional[str] = None, actor: str, commit: bool = True,
) -> Employee:
    employee = session.get(Employee, employee_id)
    if employee is None:
        raise EmployeeNotFound(employee_id)
    changes: dict = {}
    if employee_code is not None and employee_code != employee.employee_code:
        clash = session.execute(
            select(Employee.id).where(
                Employee.employee_code == employee_code, Employee.id != employee_id,
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
    if employee_type is not None and employee_type != employee.employee_type:
        changes["employee_type"] = employee_type.value
        employee.employee_type = employee_type
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
        metadata={"employee_code": employee.employee_code, "full_name": employee.full_name},
    )
    session.execute(
        delete(ViolationRemoval).where(ViolationRemoval.employee_id == employee_id)
    )
    session.delete(employee)
    if commit:
        session.commit()


# ============================================================================
# EMPLOYEE — READ
# ============================================================================

def _total_offenses_ever_subq(session: Session, employee_id: int) -> int:
    """Active violations + removed violations = total offenses ever committed."""
    active = session.execute(
        select(func.count(ViolationRecord.id)).where(ViolationRecord.employee_id == employee_id)
    ).scalar_one()
    removed = session.execute(
        select(func.count(ViolationRemoval.id)).where(ViolationRemoval.employee_id == employee_id)
    ).scalar_one()
    return active + removed


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
    min_active_violations: Optional[int] = None,
    min_total_offenses: Optional[int] = None,
    limit: int = 25,
    offset: int = 0,
) -> Sequence:
    """
    Returns Rows with:
        id, employee_code, full_name, department, position, status,
        active_violation_count, total_offenses
    """
    total_offenses_sq = (
        select(func.count(ViolationRecord.id))
        .where(ViolationRecord.employee_id == Employee.id)
        .correlate(Employee)
        .scalar_subquery()
        + select(func.count(ViolationRemoval.id))
        .where(ViolationRemoval.employee_id == Employee.id)
        .correlate(Employee)
        .scalar_subquery()
    ).label("total_offenses")

    stmt = select(
        Employee.id,
        Employee.employee_code,
        Employee.full_name,
        Employee.department,
        Employee.position,
        Employee.employee_type,
        Employee.status,
        Employee.active_violation_count,
        total_offenses_sq,
    )
    if search and (term := search.strip()):
        pattern = f"%{term}%"
        stmt = stmt.where(or_(
            Employee.first_name.ilike(pattern),
            Employee.last_name.ilike(pattern),
            Employee.employee_code.ilike(pattern),
            Employee.full_name.ilike(pattern),
        ))
    if department:
        stmt = stmt.where(Employee.department.ilike(f"%{department}%"))
    if position:
        stmt = stmt.where(Employee.position.ilike(f"%{position}%"))
    if not include_inactive:
        stmt = stmt.where(Employee.status == EmployeeStatus.active)
    if min_active_violations is not None:
        stmt = stmt.where(Employee.active_violation_count >= min_active_violations)
    if min_total_offenses is not None:
        stmt = stmt.where(total_offenses_sq >= min_total_offenses)
    stmt = stmt.order_by(Employee.last_name, Employee.first_name, Employee.id).limit(limit).offset(offset)
    return session.execute(stmt).all()


def count_employees(
    session: Session,
    *,
    search: Optional[str] = None,
    include_inactive: bool = False,
    department: Optional[str] = None,
    position: Optional[str] = None,
    min_active_violations: Optional[int] = None,
    min_total_offenses: Optional[int] = None,
) -> int:
    total_offenses = (
        select(func.count(ViolationRecord.id))
        .where(ViolationRecord.employee_id == Employee.id)
        .correlate(Employee)
        .scalar_subquery()
        + select(func.count(ViolationRemoval.id))
        .where(ViolationRemoval.employee_id == Employee.id)
        .correlate(Employee)
        .scalar_subquery()
    )
    stmt = select(func.count(Employee.id))
    if search and (term := search.strip()):
        pattern = f"%{term}%"
        stmt = stmt.where(or_(
            Employee.first_name.ilike(pattern),
            Employee.last_name.ilike(pattern),
            Employee.employee_code.ilike(pattern),
            Employee.full_name.ilike(pattern),
        ))
    if department:
        stmt = stmt.where(Employee.department.ilike(f"%{department}%"))
    if position:
        stmt = stmt.where(Employee.position.ilike(f"%{position}%"))
    if not include_inactive:
        stmt = stmt.where(Employee.status == EmployeeStatus.active)
    if min_active_violations is not None:
        stmt = stmt.where(Employee.active_violation_count >= min_active_violations)
    if min_total_offenses is not None:
        stmt = stmt.where(total_offenses >= min_total_offenses)
    return session.execute(stmt).scalar_one()


def get_employee_detail(session: Session, employee_id: int) -> Optional[Employee]:
    stmt = (
        select(Employee)
        .options(
            selectinload(Employee.violation_records)
            .joinedload(ViolationRecord.subsection)
            .joinedload(ViolationSubsection.violation_type)
        )
        .where(Employee.id == employee_id)
    )
    return session.execute(stmt).scalar_one_or_none()


def get_employee_offense_summary(session: Session, employee_id: int) -> list[dict]:
    """
    Per-subsection breakdown of an employee's offense history — active AND removed.
    Shows next offense number and what penalty would apply.
    """
    employee = session.get(Employee, employee_id)
    if employee is None:
        raise EmployeeNotFound(employee_id)

    # Group active records by subsection
    active_rows = session.execute(
        select(
            ViolationRecord.subsection_id,
            func.count(ViolationRecord.id).label("active_count"),
            func.max(ViolationRecord.offense_number).label("max_active"),
        ).where(ViolationRecord.employee_id == employee_id)
        .group_by(ViolationRecord.subsection_id)
    ).all()

    # Group removed records by subsection
    removed_rows = session.execute(
        select(
            ViolationRemoval.subsection_id,
            func.count(ViolationRemoval.id).label("removed_count"),
            func.max(ViolationRemoval.offense_number).label("max_removed"),
        ).where(ViolationRemoval.employee_id == employee_id)
        .group_by(ViolationRemoval.subsection_id)
    ).all()

    by_sub: dict[int, dict] = {}
    for r in active_rows:
        by_sub.setdefault(r.subsection_id, {"active": 0, "removed": 0, "max_offense": 0})
        by_sub[r.subsection_id]["active"] = r.active_count
        by_sub[r.subsection_id]["max_offense"] = max(by_sub[r.subsection_id]["max_offense"], r.max_active or 0)
    for r in removed_rows:
        by_sub.setdefault(r.subsection_id, {"active": 0, "removed": 0, "max_offense": 0})
        by_sub[r.subsection_id]["removed"] = r.removed_count
        by_sub[r.subsection_id]["max_offense"] = max(by_sub[r.subsection_id]["max_offense"], r.max_removed or 0)

    # Hydrate subsection + type names, look up the penalty for next offense
    result = []
    for sub_id, info in by_sub.items():
        sub = session.get(ViolationSubsection, sub_id)
        if sub is None:
            continue
        next_offense = info["max_offense"] + 1
        penalty = _lookup_penalty(session, sub_id, next_offense)
        result.append({
            "subsection_id": sub_id,
            "subsection_name": sub.name,
            "violation_type_name": sub.violation_type.name if sub.violation_type else "",
            "active_offenses": info["active"],
            "removed_offenses": info["removed"],
            "total_offenses": info["active"] + info["removed"],
            "last_offense_number": info["max_offense"],
            "next_offense_number": next_offense,
            "penalty_if_repeated": penalty.description if penalty else None,
        })
    result.sort(key=lambda x: x["subsection_name"])
    return result


def get_employee_totals(session: Session, employee_id: int) -> dict:
    employee = session.get(Employee, employee_id)
    if employee is None:
        raise EmployeeNotFound(employee_id)
    active = session.execute(
        select(func.count(ViolationRecord.id)).where(ViolationRecord.employee_id == employee_id)
    ).scalar_one()
    removed = session.execute(
        select(func.count(ViolationRemoval.id)).where(ViolationRemoval.employee_id == employee_id)
    ).scalar_one()
    return {
        "employee_id": employee_id,
        "active_violation_count": active,
        "total_offenses": active + removed,
    }


# ============================================================================
# VIOLATION TYPE — WRITE
# ============================================================================

def create_violation_type(
    session: Session, *, name: str, description: Optional[str] = None,
    is_active: bool = True, actor: str, commit: bool = True,
) -> ViolationType:
    exists = session.execute(
        select(ViolationType.id).where(ViolationType.name == name)
    ).scalar_one_or_none()
    if exists is not None:
        raise DuplicateViolationType(name)
    vtype = ViolationType(name=name, description=description, is_active=is_active)
    session.add(vtype)
    session.flush()
    log_event(
        session, actor=actor, action="violation_type.created",
        target_type="violation_type", target_id=vtype.id,
        summary=f"Added violation type '{vtype.name}'",
        metadata={"name": vtype.name},
    )
    if commit:
        session.commit()
    return vtype


def update_violation_type(
    session: Session, violation_type_id: int, *,
    name: Optional[str] = None, description: Optional[str] = None,
    actor: str, commit: bool = True,
) -> ViolationType:
    vtype = session.get(ViolationType, violation_type_id)
    if vtype is None:
        raise ViolationTypeNotFound(violation_type_id)
    changes: dict = {}
    if name is not None and name != vtype.name:
        clash = session.execute(
            select(ViolationType.id).where(
                ViolationType.name == name, ViolationType.id != violation_type_id,
            )
        ).scalar_one_or_none()
        if clash is not None:
            raise DuplicateViolationType(name)
        changes["name"] = name
        vtype.name = name
    if description is not None:
        changes["description"] = description
        vtype.description = description
    if changes:
        log_event(
            session, actor=actor, action="violation_type.updated",
            target_type="violation_type", target_id=vtype.id,
            summary=f"Updated violation type '{vtype.name}'",
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
        select(func.count(ViolationRecord.id))
        .join(ViolationSubsection, ViolationSubsection.id == ViolationRecord.subsection_id)
        .where(ViolationSubsection.violation_type_id == violation_type_id)
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
    """id, name, description — for the first-level picker."""
    stmt = (
        select(ViolationType.id, ViolationType.name, ViolationType.description)
        .where(ViolationType.is_active.is_(True))
        .order_by(ViolationType.name)
    )
    return session.execute(stmt).all()


def list_violation_types(session: Session, *, include_inactive: bool = True) -> Sequence[ViolationType]:
    stmt = select(ViolationType).order_by(ViolationType.name)
    if not include_inactive:
        stmt = stmt.where(ViolationType.is_active.is_(True))
    return session.execute(stmt).scalars().all()


def get_violation_type(session: Session, violation_type_id: int) -> Optional[ViolationType]:
    return session.get(ViolationType, violation_type_id)


# ============================================================================
# VIOLATION SUBSECTION — WRITE
# ============================================================================

def create_subsection(
    session: Session, *, violation_type_id: int, name: str,
    description: Optional[str] = None, is_active: bool = True,
    actor: str, commit: bool = True,
) -> ViolationSubsection:
    vtype = session.get(ViolationType, violation_type_id)
    if vtype is None:
        raise ViolationTypeNotFound(violation_type_id)
    dup = session.execute(
        select(ViolationSubsection.id).where(
            ViolationSubsection.violation_type_id == violation_type_id,
            ViolationSubsection.name == name,
        )
    ).scalar_one_or_none()
    if dup is not None:
        raise DuplicateSubsection(violation_type_id, name)
    sub = ViolationSubsection(
        violation_type_id=violation_type_id, name=name,
        description=description, is_active=is_active,
    )
    session.add(sub)
    session.flush()
    log_event(
        session, actor=actor, action="subsection.created",
        target_type="subsection", target_id=sub.id,
        summary=f"Added subsection '{sub.name}' under '{vtype.name}'",
        metadata={"violation_type_id": violation_type_id, "violation_type_name": vtype.name, "name": sub.name},
    )
    if commit:
        session.commit()
    return sub


def update_subsection(
    session: Session, subsection_id: int, *,
    name: Optional[str] = None, description: Optional[str] = None,
    actor: str, commit: bool = True,
) -> ViolationSubsection:
    sub = session.get(ViolationSubsection, subsection_id)
    if sub is None:
        raise SubsectionNotFound(subsection_id)
    changes: dict = {}
    if name is not None and name != sub.name:
        clash = session.execute(
            select(ViolationSubsection.id).where(
                ViolationSubsection.violation_type_id == sub.violation_type_id,
                ViolationSubsection.name == name,
                ViolationSubsection.id != subsection_id,
            )
        ).scalar_one_or_none()
        if clash is not None:
            raise DuplicateSubsection(sub.violation_type_id, name)
        changes["name"] = name
        sub.name = name
    if description is not None:
        changes["description"] = description
        sub.description = description
    if changes:
        log_event(
            session, actor=actor, action="subsection.updated",
            target_type="subsection", target_id=sub.id,
            summary=f"Updated subsection '{sub.name}'",
            metadata={"changes": changes},
        )
    if commit:
        session.commit()
    return sub


def set_subsection_active(
    session: Session, subsection_id: int, is_active: bool, *, actor: str, commit: bool = True,
) -> ViolationSubsection:
    sub = session.get(ViolationSubsection, subsection_id)
    if sub is None:
        raise SubsectionNotFound(subsection_id)
    sub.is_active = is_active
    log_event(
        session, actor=actor,
        action="subsection.activated" if is_active else "subsection.deactivated",
        target_type="subsection", target_id=sub.id,
        summary=f"{'Activated' if is_active else 'Deactivated'} subsection '{sub.name}'",
        metadata={"name": sub.name},
    )
    if commit:
        session.commit()
    return sub


def delete_subsection(session: Session, subsection_id: int, *, actor: str, commit: bool = True) -> None:
    sub = session.get(ViolationSubsection, subsection_id)
    if sub is None:
        raise SubsectionNotFound(subsection_id)
    in_use = session.execute(
        select(func.count(ViolationRecord.id)).where(ViolationRecord.subsection_id == subsection_id)
    ).scalar_one()
    if in_use:
        raise SubsectionInUse(subsection_id)
    log_event(
        session, actor=actor, action="subsection.deleted",
        target_type="subsection", target_id=sub.id,
        summary=f"Deleted subsection '{sub.name}'",
        metadata={"name": sub.name},
    )
    session.delete(sub)
    if commit:
        session.commit()


# ============================================================================
# VIOLATION SUBSECTION — READ
# ============================================================================

def list_subsections(
    session: Session, violation_type_id: int, *, include_inactive: bool = False,
) -> Sequence[ViolationSubsection]:
    stmt = (
        select(ViolationSubsection)
        .options(selectinload(ViolationSubsection.penalties))
        .where(ViolationSubsection.violation_type_id == violation_type_id)
        .order_by(ViolationSubsection.name)
    )
    if not include_inactive:
        stmt = stmt.where(ViolationSubsection.is_active.is_(True))
    return session.execute(stmt).scalars().all()


def get_subsection(session: Session, subsection_id: int) -> Optional[ViolationSubsection]:
    stmt = (
        select(ViolationSubsection)
        .options(selectinload(ViolationSubsection.penalties))
        .where(ViolationSubsection.id == subsection_id)
    )
    return session.execute(stmt).scalar_one_or_none()


# ============================================================================
# PENALTY
# ============================================================================

def replace_penalties(
    session: Session, subsection_id: int,
    penalties: list[dict],  # each: {"offense_number": int, "description": str}
    *, actor: str, commit: bool = True,
) -> ViolationSubsection:
    """Replace the full penalty ladder for a subsection."""
    sub = session.get(ViolationSubsection, subsection_id)
    if sub is None:
        raise SubsectionNotFound(subsection_id)
    # Validate offense numbers are unique and ≥ 1
    nums = [p["offense_number"] for p in penalties]
    if len(nums) != len(set(nums)):
        raise ValueError("Duplicate offense_number in penalties")
    if any(n < 1 for n in nums):
        raise ValueError("offense_number must be >= 1")
    # Delete existing
    for existing in session.execute(
        select(Penalty).where(Penalty.subsection_id == subsection_id)
    ).scalars().all():
        session.delete(existing)
    session.flush()
    # Insert new
    for p in penalties:
        session.add(Penalty(
            subsection_id=subsection_id,
            offense_number=p["offense_number"],
            description=p["description"],
        ))
    log_event(
        session, actor=actor, action="penalty.replaced",
        target_type="subsection", target_id=sub.id,
        summary=f"Set {len(penalties)} penalty tier(s) for '{sub.name}'",
        metadata={"subsection_id": subsection_id, "offense_numbers": sorted(nums)},
    )
    if commit:
        session.commit()
        session.refresh(sub)
    return sub


def _lookup_penalty(session: Session, subsection_id: int, offense_number: int) -> Optional[Penalty]:
    """Exact match on offense_number; fall back to the highest tier ≤ offense_number;
    fall back to the lowest tier if offense_number is below the minimum."""
    exact = session.execute(
        select(Penalty).where(
            Penalty.subsection_id == subsection_id,
            Penalty.offense_number == offense_number,
        )
    ).scalar_one_or_none()
    if exact:
        return exact
    below = session.execute(
        select(Penalty).where(
            Penalty.subsection_id == subsection_id,
            Penalty.offense_number <= offense_number,
        ).order_by(Penalty.offense_number.desc()).limit(1)
    ).scalar_one_or_none()
    if below:
        return below
    above = session.execute(
        select(Penalty).where(Penalty.subsection_id == subsection_id)
        .order_by(Penalty.offense_number.asc()).limit(1)
    ).scalar_one_or_none()
    return above


# ============================================================================
# VIOLATION RECORD — WRITE
# ============================================================================

def assign_violation(
    session: Session, *, employee_id: int, subsection_id: int,
    notes: Optional[str] = None, issued_at: Optional[datetime] = None,
    issued_by: Optional[str] = None, actor: str, commit: bool = True,
) -> ViolationRecord:
    employee = session.get(Employee, employee_id)
    if employee is None:
        raise EmployeeNotFound(employee_id)
    sub = session.execute(
        select(ViolationSubsection)
        .options(joinedload(ViolationSubsection.violation_type))
        .where(ViolationSubsection.id == subsection_id)
    ).scalar_one_or_none()
    if sub is None:
        raise SubsectionNotFound(subsection_id)
    if not sub.is_active:
        raise SubsectionInactive(subsection_id)
    if sub.violation_type is None or not sub.violation_type.is_active:
        raise ViolationTypeInactive(sub.violation_type_id)

    # Compute next offense number: count ever issued for this (employee, subsection)
    active = session.execute(
        select(func.count(ViolationRecord.id)).where(
            ViolationRecord.employee_id == employee_id,
            ViolationRecord.subsection_id == subsection_id,
        )
    ).scalar_one()
    removed = session.execute(
        select(func.count(ViolationRemoval.id)).where(
            ViolationRemoval.employee_id == employee_id,
            ViolationRemoval.subsection_id == subsection_id,
        )
    ).scalar_one()
    offense_number = active + removed + 1

    penalty = _lookup_penalty(session, subsection_id, offense_number)
    if penalty is None:
        raise NoPenaltyDefined(subsection_id, offense_number)

    record = ViolationRecord(
        employee_id=employee_id,
        subsection_id=subsection_id,
        issued_by=issued_by,
        issued_at=issued_at or datetime.now(timezone.utc),
        notes=notes,
        offense_number=offense_number,
        penalty_description=penalty.description,
    )
    session.add(record)
    session.flush()
    log_event(
        session, actor=actor, action="violation.assigned",
        target_type="violation", target_id=record.id, employee_id=employee_id,
        summary=(
            f"Issued '{sub.name}' to {employee.employee_code} ({employee.full_name}) "
            f"— offense #{offense_number} — penalty: {penalty.description}"
        ),
        metadata={
            "subsection_id": subsection_id,
            "subsection_name": sub.name,
            "violation_type_name": sub.violation_type.name if sub.violation_type else "",
            "offense_number": offense_number,
            "penalty_description": penalty.description,
            "issued_by": issued_by,
            "employee_code": employee.employee_code,
            "employee_full_name": employee.full_name,
        },
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


def remove_violation_record(
    session: Session, record_id: int, *, removed_by: str, reason: str, commit: bool = True,
) -> ViolationRemoval:
    record = session.execute(
        select(ViolationRecord)
        .options(
            joinedload(ViolationRecord.subsection).joinedload(ViolationSubsection.violation_type),
            joinedload(ViolationRecord.employee),
        )
        .where(ViolationRecord.id == record_id)
    ).scalar_one_or_none()
    if record is None:
        raise ViolationRecordNotFound(record_id)

    removal = ViolationRemoval(
        violation_record_id=record.id,
        subsection_id=record.subsection_id,
        subsection_name=record.subsection.name if record.subsection else "",
        violation_type_name=(
            record.subsection.violation_type.name
            if record.subsection and record.subsection.violation_type else ""
        ),
        offense_number=record.offense_number,
        penalty_description=record.penalty_description,
        original_notes=record.notes,
        original_issued_by=record.issued_by,
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
        target_type="violation", target_id=record_id, employee_id=removal.employee_id,
        summary=(
            f"Removed '{removal.subsection_name}' (offense #{removal.offense_number}) from "
            f"{removal.employee_code} ({removal.employee_full_name}) — reason: {reason}"
        ),
        metadata={
            "subsection_name": removal.subsection_name,
            "violation_type_name": removal.violation_type_name,
            "offense_number": removal.offense_number,
            "penalty_description": removal.penalty_description,
            "reason": reason,
            "employee_code": removal.employee_code,
            "employee_full_name": removal.employee_full_name,
        },
    )
    if commit:
        session.commit()
    return removal


def clear_employee_violations(
    session: Session, employee_id: int, *, removed_by: str, reason: str, commit: bool = True,
) -> int:
    employee = session.get(Employee, employee_id)
    if employee is None:
        raise EmployeeNotFound(employee_id)
    records = session.execute(
        select(ViolationRecord)
        .options(
            joinedload(ViolationRecord.subsection).joinedload(ViolationSubsection.violation_type),
            joinedload(ViolationRecord.employee),
        )
        .where(ViolationRecord.employee_id == employee_id)
    ).scalars().all()
    now = datetime.now(timezone.utc)
    for record in records:
        removal = ViolationRemoval(
            violation_record_id=record.id,
            subsection_id=record.subsection_id,
            subsection_name=record.subsection.name if record.subsection else "",
            violation_type_name=(
                record.subsection.violation_type.name
                if record.subsection and record.subsection.violation_type else ""
            ),
            offense_number=record.offense_number,
            penalty_description=record.penalty_description,
            original_notes=record.notes,
            original_issued_by=record.issued_by,
            original_issued_at=record.issued_at,
            employee_id=record.employee_id,
            employee_code=employee.employee_code,
            employee_full_name=employee.full_name,
            removed_by=removed_by, reason=reason, removed_at=now,
        )
        session.add(removal)
        session.delete(record)
        log_event(
            session, actor=removed_by, action="violation.removed",
            target_type="violation", target_id=record.id, employee_id=employee.id,
            summary=(
                f"Removed '{removal.subsection_name}' (offense #{removal.offense_number}) from "
                f"{employee.employee_code} ({employee.full_name}) — amnesty — reason: {reason}"
            ),
            metadata={
                "subsection_name": removal.subsection_name,
                "violation_type_name": removal.violation_type_name,
                "offense_number": removal.offense_number,
                "penalty_description": removal.penalty_description,
                "reason": reason,
                "amnesty": True,
                "employee_code": employee.employee_code,
                "employee_full_name": employee.full_name,
            },
        )
    if commit:
        session.commit()
    return len(records)


# ============================================================================
# VIOLATION RECORD — READ
# ============================================================================

def list_employee_violations(
    session: Session, employee_id: int, *,
    only_offense_number_gte: Optional[int] = None,
    since: Optional[datetime] = None, until: Optional[datetime] = None,
    limit: int = 100, offset: int = 0,
) -> Sequence[ViolationRecord]:
    stmt = (
        select(ViolationRecord)
        .options(
            joinedload(ViolationRecord.subsection).joinedload(ViolationSubsection.violation_type),
            joinedload(ViolationRecord.employee),
        )
        .where(ViolationRecord.employee_id == employee_id)
    )
    if only_offense_number_gte is not None:
        stmt = stmt.where(ViolationRecord.offense_number >= only_offense_number_gte)
    if since is not None:
        stmt = stmt.where(ViolationRecord.issued_at >= since)
    if until is not None:
        stmt = stmt.where(ViolationRecord.issued_at <= until)
    stmt = stmt.order_by(ViolationRecord.issued_at.desc(), ViolationRecord.id.desc())
    stmt = stmt.limit(limit).offset(offset)
    return session.execute(stmt).scalars().all()


def list_recent_violations(
    session: Session, *, days: int = 30, limit: int = 50,
) -> Sequence[ViolationRecord]:
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    stmt = (
        select(ViolationRecord)
        .options(
            joinedload(ViolationRecord.subsection).joinedload(ViolationSubsection.violation_type),
            joinedload(ViolationRecord.employee),
        )
        .where(ViolationRecord.issued_at >= cutoff)
        .order_by(ViolationRecord.issued_at.desc(), ViolationRecord.id.desc())
        .limit(limit)
    )
    return session.execute(stmt).scalars().all()


def get_violation_record(session: Session, record_id: int) -> Optional[ViolationRecord]:
    stmt = (
        select(ViolationRecord)
        .options(
            joinedload(ViolationRecord.subsection).joinedload(ViolationSubsection.violation_type),
            joinedload(ViolationRecord.employee),
        )
        .where(ViolationRecord.id == record_id)
    )
    return session.execute(stmt).scalar_one_or_none()


# ============================================================================
# VIOLATION REMOVAL — READ
# ============================================================================

def list_violation_removals(
    session: Session, *,
    employee_id: Optional[int] = None, removed_by: Optional[str] = None,
    since: Optional[datetime] = None, until: Optional[datetime] = None,
    search: Optional[str] = None, limit: int = 50, offset: int = 0,
) -> Sequence[ViolationRemoval]:
    stmt = select(ViolationRemoval).order_by(
        ViolationRemoval.removed_at.desc(), ViolationRemoval.id.desc(),
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
            ViolationRemoval.subsection_name.ilike(pattern),
            ViolationRemoval.violation_type_name.ilike(pattern),
        ))
    return session.execute(stmt.limit(limit).offset(offset)).scalars().all()


def count_violation_removals(
    session: Session, *,
    employee_id: Optional[int] = None, removed_by: Optional[str] = None,
    since: Optional[datetime] = None, until: Optional[datetime] = None,
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
            ViolationRemoval.subsection_name.ilike(pattern),
            ViolationRemoval.violation_type_name.ilike(pattern),
        ))
    return session.execute(stmt).scalar_one()


def get_violation_removal(session: Session, removal_id: int) -> Optional[ViolationRemoval]:
    return session.get(ViolationRemoval, removal_id)


# ============================================================================
# ACTIVITY — read side (unchanged shape)
# ============================================================================

def list_activity_events(
    session: Session, *,
    day: Optional[date] = None, start: Optional[date] = None, end: Optional[date] = None,
    actor: Optional[str] = None, action: Optional[str] = None,
    target_type: Optional[str] = None, employee_id: Optional[int] = None,
    limit: int = 50, offset: int = 0,
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
    session: Session, *,
    day: Optional[date] = None, start: Optional[date] = None, end: Optional[date] = None,
    actor: Optional[str] = None, action: Optional[str] = None,
    target_type: Optional[str] = None, employee_id: Optional[int] = None,
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
    stmt = (
        select(
            ActivityEvent.event_date,
            func.count(ActivityEvent.id).label("total"),
            func.sum(case((ActivityEvent.target_type == "employee", 1), else_=0)).label("employees"),
            func.sum(case((ActivityEvent.target_type == "violation", 1), else_=0)).label("violations"),
            func.sum(case((ActivityEvent.target_type.in_(["violation_type", "subsection"]), 1), else_=0)).label("violation_types"),
            func.sum(case((ActivityEvent.action == "violation.removed", 1), else_=0)).label("removals"),
        )
        .where(ActivityEvent.event_date >= start, ActivityEvent.event_date <= end)
        .group_by(ActivityEvent.event_date)
        .order_by(ActivityEvent.event_date)
    )
    return session.execute(stmt).all()


def get_daily_digest_events(session: Session, day: date) -> Sequence[ActivityEvent]:
    stmt = (
        select(ActivityEvent)
        .where(ActivityEvent.event_date == day)
        .order_by(ActivityEvent.occurred_at.asc(), ActivityEvent.id.asc())
    )
    return session.execute(stmt).scalars().all()


# ============================================================================
# ANALYTICS
# ============================================================================

def top_offenders(
    session: Session, *, limit: int = 10, by: str = "active",
) -> Sequence:
    """by: 'active' = current violations, 'total' = all-time including removed."""
    if by == "active":
        order_col = Employee.active_violation_count
    elif by == "total":
        order_col = (
            select(func.count(ViolationRecord.id))
            .where(ViolationRecord.employee_id == Employee.id)
            .correlate(Employee)
            .scalar_subquery()
            + select(func.count(ViolationRemoval.id))
            .where(ViolationRemoval.employee_id == Employee.id)
            .correlate(Employee)
            .scalar_subquery()
        )
    else:
        raise ValueError("by must be 'active' or 'total'")

    stmt = (
        select(
            Employee.id,
            Employee.employee_code,
            Employee.full_name,
            Employee.department,
            Employee.active_violation_count,
            (
                select(func.count(ViolationRecord.id))
                .where(ViolationRecord.employee_id == Employee.id)
                .correlate(Employee)
                .scalar_subquery()
                + select(func.count(ViolationRemoval.id))
                .where(ViolationRemoval.employee_id == Employee.id)
                .correlate(Employee)
                .scalar_subquery()
            ).label("total_offenses"),
        )
        .where(Employee.status == EmployeeStatus.active)
        .order_by(order_col.desc(), Employee.id)
        .limit(limit)
    )
    return session.execute(stmt).all()


def department_summary(session: Session) -> Sequence:
    active_rows = session.execute(
        select(Employee.department, func.count(ViolationRecord.id).label("c"))
        .join(ViolationRecord, ViolationRecord.employee_id == Employee.id, isouter=True)
        .where(Employee.status == EmployeeStatus.active)
        .group_by(Employee.department)
    ).all()
    active_map = {(r.department or ""): r.c for r in active_rows}

    removed_rows = session.execute(
        select(func.count(ViolationRemoval.id)).group_by(ViolationRemoval.employee_id)
    ).all()

    employees_rows = session.execute(
        select(Employee.department, func.count(Employee.id).label("c"))
        .where(Employee.status == EmployeeStatus.active)
        .group_by(Employee.department)
    ).all()

    out = []
    for r in employees_rows:
        dept = r.department
        out.append({
            "department": dept,
            "employees": r.c,
            "active_violations": active_map.get(dept or "", 0),
        })
    out.sort(key=lambda x: x["active_violations"], reverse=True)
    return out


def subsection_frequency(session: Session, *, limit: int = 20) -> Sequence:
    stmt = (
        select(
            ViolationSubsection.id,
            ViolationSubsection.name.label("subsection_name"),
            ViolationType.name.label("violation_type_name"),
            func.count(ViolationRecord.id).label("times_issued"),
            func.max(ViolationRecord.offense_number).label("max_offense_number"),
        )
        .join(ViolationRecord, ViolationRecord.subsection_id == ViolationSubsection.id, isouter=True)
        .join(ViolationType, ViolationType.id == ViolationSubsection.violation_type_id)
        .group_by(ViolationSubsection.id)
        .order_by(func.count(ViolationRecord.id).desc())
        .limit(limit)
    )
    return session.execute(stmt).all()


def activity_over_time(session: Session, *, days: int = 30, bucket: str = "day") -> Sequence:
    fmt = {"day": "%Y-%m-%d", "week": "%Y-W%W", "month": "%Y-%m"}.get(bucket)
    if fmt is None:
        raise ValueError("bucket must be 'day', 'week', or 'month'")
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    stmt = (
        select(
            func.strftime(fmt, ViolationRecord.issued_at).label("bucket"),
            func.count(ViolationRecord.id).label("count"),
        )
        .where(ViolationRecord.issued_at >= cutoff)
        .group_by("bucket")
        .order_by("bucket")
    )
    return session.execute(stmt).all()


def employees_with_repeat_offenses(
    session: Session, *, min_offense_number: int = 2,
) -> Sequence:
    """Employees who have reached at least `min_offense_number` on any single subsection,
    counting both active and removed records."""
    rec = select(
        ViolationRecord.employee_id.label("employee_id"),
        ViolationRecord.subsection_id.label("subsection_id"),
        ViolationRecord.offense_number.label("offense_number"),
    )
    rem = select(
        ViolationRemoval.employee_id.label("employee_id"),
        ViolationRemoval.subsection_id.label("subsection_id"),
        ViolationRemoval.offense_number.label("offense_number"),
    )
    unioned = union_all(rec, rem).subquery()
    max_per_emp = (
        select(
            unioned.c.employee_id,
            func.max(unioned.c.offense_number).label("max_offense"),
            func.count().label("total_offenses"),
        )
        .group_by(unioned.c.employee_id)
        .having(func.max(unioned.c.offense_number) >= min_offense_number)
        .subquery()
    )
    stmt = (
        select(
            Employee.id,
            Employee.employee_code,
            Employee.full_name,
            Employee.department,
            max_per_emp.c.max_offense,
            max_per_emp.c.total_offenses,
        )
        .join(max_per_emp, max_per_emp.c.employee_id == Employee.id)
        .where(Employee.status == EmployeeStatus.active)
        .order_by(max_per_emp.c.max_offense.desc(), max_per_emp.c.total_offenses.desc())
    )
    return session.execute(stmt).all()


def violation_free_employees(session: Session, *, since: Optional[datetime] = None) -> Sequence:
    subq = select(ViolationRecord.employee_id)
    if since is not None:
        subq = subq.where(ViolationRecord.issued_at >= since)
    stmt = (
        select(
            Employee.id, Employee.employee_code, Employee.full_name, Employee.department,
        )
        .where(
            Employee.status == EmployeeStatus.active,
            Employee.id.not_in(subq),
        )
        .order_by(Employee.last_name, Employee.first_name)
    )
    return session.execute(stmt).all()

# ============================================================================
# EMPLOYEE — full violation history (active + removed)
# ============================================================================

def list_employee_violation_history(
    session: Session, employee_id: int, *,
    status: Optional[str] = None,           # "active" | "removed" | None (both)
    subsection_id: Optional[int] = None,
    since: Optional[datetime] = None,       # inclusive, on original issued_at
    until: Optional[datetime] = None,
    limit: int = 100,
    offset: int = 0,
) -> Sequence:
    """
    Union of current ViolationRecord rows and ViolationRemoval snapshots,
    ordered by issued_at DESC so the history reads like a timeline.
    Each row carries a `status` discriminator: "active" or "removed".
    """
    active_q = select(
        literal("active", type_=String(10)).label("status"),
        ViolationRecord.id.label("violation_record_id"),
        ViolationRecord.subsection_id,
        ViolationSubsection.name.label("subsection_name"),
        ViolationType.name.label("violation_type_name"),
        ViolationRecord.offense_number,
        ViolationRecord.penalty_description,
        ViolationRecord.notes,
        ViolationRecord.issued_by,
        ViolationRecord.issued_at,
        cast(null(), String).label("removed_by"),
        cast(null(), Text).label("removal_reason"),
        cast(null(), DateTime()).label("removed_at"),
    ).select_from(ViolationRecord).join(
        ViolationSubsection, ViolationSubsection.id == ViolationRecord.subsection_id, isouter=True,
    ).join(
        ViolationType, ViolationType.id == ViolationSubsection.violation_type_id, isouter=True,
    ).where(ViolationRecord.employee_id == employee_id)

    removed_q = select(
        literal("removed", type_=String(10)).label("status"),
        ViolationRemoval.violation_record_id,
        ViolationRemoval.subsection_id,
        ViolationRemoval.subsection_name,
        ViolationRemoval.violation_type_name,
        ViolationRemoval.offense_number,
        ViolationRemoval.penalty_description,
        ViolationRemoval.original_notes.label("notes"),
        ViolationRemoval.original_issued_by.label("issued_by"),
        ViolationRemoval.original_issued_at.label("issued_at"),
        ViolationRemoval.removed_by,
        ViolationRemoval.reason.label("removal_reason"),
        ViolationRemoval.removed_at,
    ).where(ViolationRemoval.employee_id == employee_id)

    if subsection_id is not None:
        active_q = active_q.where(ViolationRecord.subsection_id == subsection_id)
        removed_q = removed_q.where(ViolationRemoval.subsection_id == subsection_id)
    if since is not None:
        active_q = active_q.where(ViolationRecord.issued_at >= since)
        removed_q = removed_q.where(ViolationRemoval.original_issued_at >= since)
    if until is not None:
        active_q = active_q.where(ViolationRecord.issued_at <= until)
        removed_q = removed_q.where(ViolationRemoval.original_issued_at <= until)

    parts = []
    if status in (None, "active"):
        parts.append(active_q)
    if status in (None, "removed"):
        parts.append(removed_q)
    if not parts:
        return []

    if len(parts) == 1:
        return session.execute(parts[0].limit(limit).offset(offset)).all()

    union_q = union_all(*parts).subquery()
    stmt = (
        select(union_q)
        .order_by(union_q.c.issued_at.desc(), union_q.c.violation_record_id.desc())
        .limit(limit).offset(offset)
    )
    return session.execute(stmt).all()


def count_employee_violation_history(
    session: Session, employee_id: int, *,
    status: Optional[str] = None,
    subsection_id: Optional[int] = None,
    since: Optional[datetime] = None,
    until: Optional[datetime] = None,
) -> int:
    total = 0
    if status in (None, "active"):
        stmt = select(func.count(ViolationRecord.id)).where(ViolationRecord.employee_id == employee_id)
        if subsection_id is not None:
            stmt = stmt.where(ViolationRecord.subsection_id == subsection_id)
        if since is not None:
            stmt = stmt.where(ViolationRecord.issued_at >= since)
        if until is not None:
            stmt = stmt.where(ViolationRecord.issued_at <= until)
        total += session.execute(stmt).scalar_one()
    if status in (None, "removed"):
        stmt = select(func.count(ViolationRemoval.id)).where(ViolationRemoval.employee_id == employee_id)
        if subsection_id is not None:
            stmt = stmt.where(ViolationRemoval.subsection_id == subsection_id)
        if since is not None:
            stmt = stmt.where(ViolationRemoval.original_issued_at >= since)
        if until is not None:
            stmt = stmt.where(ViolationRemoval.original_issued_at <= until)
        total += session.execute(stmt).scalar_one()
    return total
