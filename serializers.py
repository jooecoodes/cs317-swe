from models import Employee, ViolationRecord

def employee_search_row(row) -> dict:
    return {
        "id": row.id,
        "full_name": row.full_name,
        "employee_code": row.employee_code,
        "department": row.department,
        "position": row.position,
        "total_points": row.total_points,
        "total_strikes": row.total_strikes,
    }


def violation_record_dict(record: ViolationRecord) -> dict:
    return {
        "id": record.id,
        "type_name": record.violation_type.name if record.violation_type else None,
        "points": record.points,
        "is_strike": record.is_strike,
        "issued_at": record.issued_at,
        "issued_by": record.issued_by,
        "notes": record.notes,
    }


def employee_detail_dict(employee: Employee) -> dict:
    return {
        "id": employee.id,
        "employee_code": employee.employee_code,
        "first_name": employee.first_name,
        "last_name": employee.last_name,
        "department": employee.department,
        "position": employee.position,
        "total_points": employee.total_points,
        "total_strikes": employee.total_strikes,
        "violations": [violation_record_dict(r) for r in employee.violation_records],
    }
