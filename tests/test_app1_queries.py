"""
Tier-1 tests for the queries.py data layer — edge cases, error paths,
and filter variants not covered by test_app1*.py.

Targets (from coverage report, 122 missing lines in queries.py):
  * 404 paths: EmployeeNotFound, ViolationTypeNotFound, ViolationRecordNotFound
  * 400/409 paths: ViolationTypeInactive, DuplicateEmployeeCode,
                   DuplicateViolationType
  * filter variants: only_strikes, since/until, by=strikes/records,
                     bucket=week/month, position
  * update paths that mutate employee_code, notes, default_points, is_strike
  * removals search / removed_by
  * activity timeline target_type / employee_id / date range / day
"""
from datetime import datetime, timedelta, timezone

ACTOR = {"X-Actor": "test"}


# ---------------------------------------------------------------- helpers

def _emp(client, code, first="Alice", last="Smith", **kw):
    body = {"employee_code": code, "first_name": first, "last_name": last}
    body.update(kw)
    r = client.post("/employees", json=body, headers=ACTOR)
    assert r.status_code == 201, r.text
    return r.json()


def _vtype(client, name, points=0, strike=False, active=True):
    r = client.post("/violation-types", json={
        "name": name, "default_points": points,
        "is_strike": strike, "is_active": active,
    }, headers=ACTOR)
    assert r.status_code == 201, r.text
    return r.json()


def _assign(client, emp_id, vt_id, **kw):
    body = {"violation_type_id": vt_id}
    body.update(kw)
    r = client.post(f"/employees/{emp_id}/violations", json=body, headers=ACTOR)
    assert r.status_code == 201, r.text
    return r.json()


# ---------------------------------------------------------------- 404 paths
# These hit the queries-layer exceptions (not router-level HTTPException),
# so they cover the exception class bodies in queries.py.

def test_update_employee_404(app1_client):
    r = app1_client.patch("/employees/99999", json={"first_name": "X"}, headers=ACTOR)
    assert r.status_code == 404
    assert r.json()["error"] == "EmployeeNotFound"


def test_deactivate_employee_404(app1_client):
    r = app1_client.post("/employees/99999/deactivate", headers=ACTOR)
    assert r.status_code == 404
    assert r.json()["error"] == "EmployeeNotFound"


def test_reactivate_employee_404(app1_client):
    r = app1_client.post("/employees/99999/reactivate", headers=ACTOR)
    assert r.status_code == 404


def test_delete_employee_404(app1_client):
    r = app1_client.delete("/employees/99999", headers=ACTOR)
    assert r.status_code == 404


def test_totals_employee_404(app1_client):
    """totals uses queries.get_employee_totals → raises EmployeeNotFound."""
    r = app1_client.get("/employees/99999/totals")
    assert r.status_code == 404
    assert r.json()["error"] == "EmployeeNotFound"


def test_update_violation_type_404(app1_client):
    r = app1_client.patch("/violation-types/99999", json={"name": "X"}, headers=ACTOR)
    assert r.status_code == 404
    assert r.json()["error"] == "ViolationTypeNotFound"


def test_activate_violation_type_404(app1_client):
    r = app1_client.post("/violation-types/99999/activate", headers=ACTOR)
    assert r.status_code == 404


def test_deactivate_violation_type_404(app1_client):
    r = app1_client.post("/violation-types/99999/deactivate", headers=ACTOR)
    assert r.status_code == 404


def test_delete_violation_type_404(app1_client):
    r = app1_client.delete("/violation-types/99999", headers=ACTOR)
    assert r.status_code == 404


def test_assign_violation_missing_employee(app1_client):
    vt = _vtype(app1_client, "Any")
    r = app1_client.post(
        "/employees/99999/violations",
        json={"violation_type_id": vt["id"]}, headers=ACTOR,
    )
    assert r.status_code == 404
    assert r.json()["error"] == "EmployeeNotFound"


def test_assign_violation_missing_vtype(app1_client):
    emp = _emp(app1_client, "E_MISS_VT")
    r = app1_client.post(
        f"/employees/{emp['id']}/violations",
        json={"violation_type_id": 99999}, headers=ACTOR,
    )
    assert r.status_code == 404
    assert r.json()["error"] == "ViolationTypeNotFound"


def test_update_violation_record_404(app1_client):
    r = app1_client.patch("/violations/99999", json={"notes": "x"}, headers=ACTOR)
    assert r.status_code == 404
    assert r.json()["error"] == "ViolationRecordNotFound"


def test_remove_violation_record_404(app1_client):
    r = app1_client.post(
        "/violations/99999/remove",
        json={"removed_by": "HR", "reason": "test"},
    )
    assert r.status_code == 404


def test_clear_violations_missing_employee(app1_client):
    r = app1_client.post(
        "/employees/99999/violations/clear",
        json={"removed_by": "HR", "reason": "test"},
    )
    assert r.status_code == 404


# ---------------------------------------------------------------- 400 / 409

def test_assign_violation_inactive_type(app1_client):
    emp = _emp(app1_client, "E_INACT")
    vt = _vtype(app1_client, "Deactivated type", active=False)
    r = app1_client.post(
        f"/employees/{emp['id']}/violations",
        json={"violation_type_id": vt["id"]}, headers=ACTOR,
    )
    assert r.status_code == 400
    assert r.json()["error"] == "ViolationTypeInactive"


def test_create_duplicate_violation_type_name(app1_client):
    _vtype(app1_client, "DupName")
    r = app1_client.post(
        "/violation-types", json={"name": "DupName"}, headers=ACTOR,
    )
    assert r.status_code == 409
    assert r.json()["error"] == "DuplicateViolationType"


def test_update_employee_to_duplicate_code(app1_client):
    _emp(app1_client, "DUP_A")
    b = _emp(app1_client, "DUP_B")
    r = app1_client.patch(
        f"/employees/{b['id']}",
        json={"employee_code": "DUP_A"}, headers=ACTOR,
    )
    assert r.status_code == 409
    assert r.json()["error"] == "DuplicateEmployeeCode"


def test_update_violation_type_to_duplicate_name(app1_client):
    _vtype(app1_client, "NameA")
    b = _vtype(app1_client, "NameB")
    r = app1_client.patch(
        f"/violation-types/{b['id']}",
        json={"name": "NameA"}, headers=ACTOR,
    )
    assert r.status_code == 409
    assert r.json()["error"] == "DuplicateViolationType"


def test_bulk_create_duplicate(app1_client):
    _emp(app1_client, "BULK_DUP")
    r = app1_client.post("/employees/bulk", json=[
        {"employee_code": "BULK_NEW", "first_name": "A", "last_name": "A"},
        {"employee_code": "BULK_DUP", "first_name": "B", "last_name": "B"},
    ], headers=ACTOR)
    assert r.status_code == 409
    assert r.json()["error"] == "DuplicateEmployeeCode"


# ---------------------------------------------------------------- update paths

def test_update_employee_all_fields(app1_client):
    emp = _emp(app1_client, "UPD_ALL", first="Old", last="Name", department="A")
    r = app1_client.patch(f"/employees/{emp['id']}", json={
        "employee_code": "UPD_ALL_2",
        "first_name": "New",
        "last_name": "Name2",
        "department": "B",
        "position": "Manager",
    }, headers=ACTOR)
    assert r.status_code == 200
    body = r.json()
    assert body["employee_code"] == "UPD_ALL_2"
    assert body["full_name"] == "New Name2"
    assert body["department"] == "B"
    assert body["position"] == "Manager"

    # Activity event recorded with changes metadata
    r = app1_client.get("/activity/timeline?action=employee.updated")
    items = r.json()["items"]
    assert len(items) >= 1
    assert "employee_code" in items[0]["metadata_json"]["changes"]


def test_update_violation_record_fields(app1_client):
    emp = _emp(app1_client, "UPD_REC")
    vt = _vtype(app1_client, "V", points=5)
    rec = _assign(app1_client, emp["id"], vt["id"])

    r = app1_client.patch(f"/violations/{rec['id']}", json={
        "notes": "updated notes", "issued_by": "Manager X",
    }, headers=ACTOR)
    assert r.status_code == 200
    body = r.json()
    assert body["notes"] == "updated notes"
    assert body["issued_by"] == "Manager X"
    assert body["points"] == 5  # points are snapshot — never editable


def test_update_violation_type_fields(app1_client):
    vt = _vtype(app1_client, "VT_OLD", points=3)
    r = app1_client.patch(f"/violation-types/{vt['id']}", json={
        "name": "VT_NEW", "description": "desc",
        "default_points": 7, "is_strike": True,
    }, headers=ACTOR)
    assert r.status_code == 200
    body = r.json()
    assert body["name"] == "VT_NEW"
    assert body["description"] == "desc"
    assert body["default_points"] == 7
    assert body["is_strike"] is True


# ---------------------------------------------------------------- filter variants

def test_list_employee_violations_only_strikes(app1_client):
    emp = _emp(app1_client, "F_STR")
    s = _vtype(app1_client, "Strike", strike=True)
    ns = _vtype(app1_client, "NonStrike", strike=False)
    _assign(app1_client, emp["id"], s["id"])
    _assign(app1_client, emp["id"], ns["id"])

    r = app1_client.get(f"/employees/{emp['id']}/violations?only_strikes=true")
    assert len(r.json()) == 1 and r.json()[0]["is_strike"] is True

    r = app1_client.get(f"/employees/{emp['id']}/violations?only_strikes=false")
    assert len(r.json()) == 1 and r.json()[0]["is_strike"] is False


def test_list_employee_violations_since_until(app1_client):
    emp = _emp(app1_client, "F_DT")
    vt = _vtype(app1_client, "Any", points=1)
    _assign(app1_client, emp["id"], vt["id"])

    now = datetime.now(timezone.utc)
    since = (now - timedelta(minutes=5)).isoformat()
    until = (now + timedelta(minutes=5)).isoformat()

    r = app1_client.get(
        f"/employees/{emp['id']}/violations",
        params={"since": since, "until": until},
    )
    assert r.status_code == 200, r.text
    assert len(r.json()) == 1

    future = (now + timedelta(hours=1)).isoformat()
    r = app1_client.get(
        f"/employees/{emp['id']}/violations",
        params={"since": future},
    )
    assert r.status_code == 200, r.text
    assert r.json() == []

def test_list_recent_violations_only_strikes(app1_client):
    emp = _emp(app1_client, "F_REC")
    s = _vtype(app1_client, "S", strike=True)
    ns = _vtype(app1_client, "NS", strike=False)
    _assign(app1_client, emp["id"], s["id"])
    _assign(app1_client, emp["id"], ns["id"])

    r = app1_client.get("/violations/recent?only_strikes=true")
    assert all(v["is_strike"] for v in r.json())


def test_analytics_top_offenders_by_strikes(app1_client):
    a = _emp(app1_client, "OFF_A", first="A", last="A")
    b = _emp(app1_client, "OFF_B", first="B", last="B")
    vt = _vtype(app1_client, "S", strike=True)
    for _ in range(3):
        _assign(app1_client, a["id"], vt["id"])
    _assign(app1_client, b["id"], vt["id"])

    r = app1_client.get("/analytics/top-offenders?by=strikes")
    codes = [e["employee_code"] for e in r.json()]
    assert codes[0] == "OFF_A"
    assert codes[1] == "OFF_B"


def test_analytics_top_offenders_by_records(app1_client):
    a = _emp(app1_client, "REC_A", first="A", last="A")
    b = _emp(app1_client, "REC_B", first="B", last="B")
    vt = _vtype(app1_client, "Any", points=0)
    for _ in range(3):
        _assign(app1_client, a["id"], vt["id"])
    _assign(app1_client, b["id"], vt["id"])

    r = app1_client.get("/analytics/top-offenders?by=records")
    assert [e["employee_code"] for e in r.json()][0] == "REC_A"


def test_analytics_activity_week_bucket(app1_client):
    emp = _emp(app1_client, "WK")
    vt = _vtype(app1_client, "V", points=1)
    _assign(app1_client, emp["id"], vt["id"])

    r = app1_client.get("/analytics/activity?bucket=week")
    assert r.status_code == 200
    body = r.json()
    assert len(body) >= 1
    assert "W" in body[0]["bucket"]   # strftime %Y-W%W


def test_analytics_activity_month_bucket(app1_client):
    emp = _emp(app1_client, "MO")
    vt = _vtype(app1_client, "V", points=1)
    _assign(app1_client, emp["id"], vt["id"])

    r = app1_client.get("/analytics/activity?bucket=month")
    assert r.status_code == 200
    body = r.json()
    assert len(body) >= 1
    assert body[0]["bucket"].count("-") == 1   # "YYYY-MM"


def test_violation_free_employees_with_since(app1_client):
    emp_a = _emp(app1_client, "CLEAN_A", first="A", last="A")
    emp_b = _emp(app1_client, "CLEAN_B", first="B", last="B")
    vt = _vtype(app1_client, "V", points=1)
    _assign(app1_client, emp_b["id"], vt["id"])

    r = app1_client.get("/analytics/clean-employees")
    assert r.status_code == 200, r.text
    codes = {e["employee_code"] for e in r.json()}
    assert "CLEAN_A" in codes and "CLEAN_B" not in codes

    future = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
    r = app1_client.get("/analytics/clean-employees", params={"since": future})
    assert r.status_code == 200, r.text
    codes = {e["employee_code"] for e in r.json()}
    assert "CLEAN_A" in codes and "CLEAN_B" in codes

# ---------------------------------------------------------------- removals filters

def test_removals_search(app1_client):
    emp = _emp(app1_client, "REM_S")
    vt = _vtype(app1_client, "Late", points=1)
    rec = _assign(app1_client, emp["id"], vt["id"])
    app1_client.post(
        f"/violations/{rec['id']}/remove",
        json={"removed_by": "HR", "reason": "amnesty Q4"},
    )

    r = app1_client.get("/violation-removals?search=amnesty")
    assert r.json()["total"] == 1

    r = app1_client.get("/violation-removals?search=nomatch")
    assert r.json()["total"] == 0


def test_removals_filter_by_removed_by(app1_client):
    emp = _emp(app1_client, "REM_B")
    vt = _vtype(app1_client, "V", points=1)
    rec = _assign(app1_client, emp["id"], vt["id"])
    app1_client.post(
        f"/violations/{rec['id']}/remove",
        json={"removed_by": "HR-Manager", "reason": "test"},
    )

    # ilike — case-insensitive substring
    r = app1_client.get("/violation-removals?removed_by=hr-manager")
    assert r.json()["total"] == 1


# ---------------------------------------------------------------- activity filters

def test_activity_timeline_target_type_filter(app1_client):
    _emp(app1_client, "AT_1")
    _vtype(app1_client, "AT_VT")

    r = app1_client.get("/activity/timeline?target_type=employee")
    items = r.json()["items"]
    assert len(items) >= 1
    assert all(e["target_type"] == "employee" for e in items)

    r = app1_client.get("/activity/timeline?target_type=violation_type")
    items = r.json()["items"]
    assert len(items) >= 1
    assert all(e["target_type"] == "violation_type" for e in items)


def test_activity_timeline_employee_id_filter(app1_client):
    emp = _emp(app1_client, "AT_EMP")
    _emp(app1_client, "AT_OTHER")

    r = app1_client.get(f"/activity/timeline?employee_id={emp['id']}")
    items = r.json()["items"]
    assert len(items) >= 1
    assert all(e["employee_id"] == emp["id"] for e in items)


def test_activity_timeline_date_range(app1_client):
    _emp(app1_client, "AT_DT")
    today = datetime.now(timezone.utc).date().isoformat()

    r = app1_client.get(f"/activity/timeline?start={today}&end={today}")
    assert r.json()["total"] >= 1

    r = app1_client.get("/activity/timeline?start=2099-01-01&end=2099-01-02")
    assert r.json()["total"] == 0


def test_activity_timeline_day_filter(app1_client):
    _emp(app1_client, "AT_DAY")
    today = datetime.now(timezone.utc).date().isoformat()
    r = app1_client.get(f"/activity/timeline?day={today}")
    assert r.json()["total"] >= 1


# ---------------------------------------------------------------- search: position

def test_search_by_position(app1_client):
    _emp(app1_client, "POS_1", position="Engineer")
    _emp(app1_client, "POS_2", position="Manager")
    r = app1_client.get("/employees?position=Engineer")
    assert [e["employee_code"] for e in r.json()["items"]] == ["POS_1"]
