"""
Function reference / scaffold for the SQLAlchemy layer.

Pattern for every call:
    1. call the function      ->  result = q.some_function(session, ...)
    2. store it in a variable
    3. print it               ->  pprint(result)
    4. inspect the DB         ->  see "WHERE TO LOOK IN THE DB" at the bottom

Uncomment the lines you want to run, one block at a time. Re-run with:
    python showcase.py

Everything lives in one `with SessionLocal() as s:` block so the session
is shared across calls. That mirrors what the endpoint layer will do later.
"""

from pprint import pprint
from datetime import datetime, timedelta, timezone

from db import SessionLocal
import queries as q
from serializers import employee_detail_dict, employee_search_row


with SessionLocal() as s:

    # ==================================================================
    # EMPLOYEE — WRITE
    # ==================================================================

    # emp = q.create_employee(
    #     s,
    #     employee_code="EMP-100",
    #     first_name="John",
    #     last_name="Doe",
    #     department="Sales",
    #     position="Associate",
    # )
    # pprint(emp)

    # emps = q.create_employees_bulk(s, [
    #     dict(employee_code="EMP-101", first_name="Jane", last_name="Smith",
    #          department="Sales", position="Senior Associate"),
    #     dict(employee_code="EMP-102", first_name="Mike", last_name="Brown",
    #          department="Warehouse", position="Forklift Operator"),
    # ])
    # pprint(emps)

    # emp = q.update_employee(s, employee_id=1, position="Senior Associate")
    # pprint(emp)

    # emp = q.set_employee_status(s, employee_id=1, status="inactive")
    # pprint(emp)

    # emp = q.deactivate_employee(s, employee_id=1)
    # pprint(emp)

    # emp = q.reactivate_employee(s, employee_id=1)
    # pprint(emp)

    # q.delete_employee(s, employee_id=1)


    # ==================================================================
    # EMPLOYEE — READ
    # ==================================================================

    # emp = q.get_employee(s, employee_id=1)
    # pprint(emp)

    # emp = q.get_employee_by_code(s, "EMP-100")
    # pprint(emp)

    # rows = q.search_employees(s, search="john")
    # pprint([employee_search_row(r) for r in rows])

    # rows = q.search_employees(s, search="EMP-10")
    # pprint([employee_search_row(r) for r in rows])

    # rows = q.search_employees(s, department="Sales")
    # pprint([employee_search_row(r) for r in rows])

    # rows = q.search_employees(s, min_points=5)
    # pprint([employee_search_row(r) for r in rows])

    # rows = q.search_employees(s, min_strikes=1)
    # pprint([employee_search_row(r) for r in rows])

    # rows = q.search_employees(s, include_inactive=True)
    # pprint([employee_search_row(r) for r in rows])

    # n = q.count_employees(s)
    # print(n)

    emp = q.get_employee_detail(s, employee_id=1)
    pprint(employee_detail_dict(emp) if emp else None)


    # ==================================================================
    # VIOLATION TYPE — WRITE
    # ==================================================================

    # vt = q.create_violation_type(
    #     s,
    #     name="Late",
    #     description="Arrived late to shift",
    #     default_points=1,
    #     is_strike=False,
    # )
    # pprint(vt)

    # vt = q.update_violation_type(s, violation_type_id=1, default_points=2)
    # pprint(vt)

    # vt = q.set_violation_type_active(s, violation_type_id=1, is_active=False)
    # pprint(vt)

    # q.delete_violation_type(s, violation_type_id=1)   # raises if in use


    # ==================================================================
    # VIOLATION TYPE — READ
    # ==================================================================

    # rows = q.get_active_violation_types(s)          # dropdown view
    # pprint([dict(r._mapping) for r in rows])

    # vts = q.list_violation_types(s, include_inactive=True)
    # pprint(vts)

    # vts = q.list_violation_types(s, only_strikes=True)
    # pprint(vts)

    # vt = q.get_violation_type(s, violation_type_id=1)
    # pprint(vt)


    # ==================================================================
    # VIOLATION RECORD — WRITE
    # ==================================================================

    # rec = q.assign_violation(
    #     s,
    #     employee_id=1,
    #     violation_type_id=1,
    #     notes="Arrived 30 minutes late.",
    #     issued_by="HR-Admin",
    #     issued_at=datetime.now(timezone.utc),
    # )
    # pprint(rec)

    # rec = q.update_violation_record(s, record_id=1, notes="Corrected note.")
    # pprint(rec)

    # q.delete_violation_record(s, record_id=1)

    # n = q.clear_employee_violations(s, employee_id=1)
    # print(f"cleared {n} records")


    # ==================================================================
    # VIOLATION RECORD — READ
    # ==================================================================

    # recs = q.list_employee_violations(s, employee_id=1)
    # pprint(recs)

    # recs = q.list_employee_violations(s, employee_id=1, only_strikes=True)
    # pprint(recs)

    # recs = q.list_employee_violations(
    #     s, employee_id=1,
    #     since=datetime.now(timezone.utc) - timedelta(days=30),
    # )
    # pprint(recs)

    # recs = q.list_recent_violations(s, days=30)
    # pprint(recs)

    # recs = q.list_recent_violations(s, days=30, only_strikes=True)
    # pprint(recs)

    # rec = q.get_violation_record(s, record_id=1)
    # pprint(rec)


    # ==================================================================
    # ANALYTICS
    # ==================================================================

    # totals = q.get_employee_totals(s, employee_id=1)
    # pprint(totals)

    # rows = q.top_offenders(s, limit=5, by="points")   # or "strikes" / "records"
    # pprint([dict(r._mapping) for r in rows])

    # rows = q.department_summary(s)
    # pprint(rows)

    # rows = q.violation_type_frequency(s)
    # pprint([dict(r._mapping) for r in rows])

    # rows = q.activity_over_time(s, days=30, bucket="week")   # or "day" / "month"
    # pprint([dict(r._mapping) for r in rows])

    # rows = q.employees_with_repeat_strikes(s, min_strikes=2)
    # pprint([dict(r._mapping) for r in rows])

    # rows = q.violation_free_employees(s)
    # pprint([dict(r._mapping) for r in rows])

    pass
