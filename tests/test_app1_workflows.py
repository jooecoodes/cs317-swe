"""
Multi-step integration flows for app1. Each test exercises a sequence
of API calls and verifies state at the end — this is where audit-log
and cascade behavior live.
"""
ACTOR = {"X-Actor": "test"}


def _emp(client, code, first="Alice", last="Smith", **kw):
    body = {"employee_code": code, "first_name": first, "last_name": last}
    body.update(kw)
    r = client.post("/employees", json=body, headers=ACTOR)
    assert r.status_code == 201, r.text
    return r.json()


def _vtype(client, name):
    r = client.post("/violation-types", json={"name": name}, headers=ACTOR)
    assert r.status_code == 201, r.text
    return r.json()


def _punishable_subsection(client, vtype):
    r = client.post(
        f"/violation-types/{vtype['id']}/subsections",
        json={"name": "Default"}, headers=ACTOR,
    )
    assert r.status_code == 201, r.text
    subsection = r.json()
    r = client.put(
        f"/subsections/{subsection['id']}/penalties",
        json={"penalties": [
            {"offense_number": 1, "description": "Verbal warning"},
            {"offense_number": 2, "description": "Written warning"},
        ]},
        headers=ACTOR,
    )
    assert r.status_code == 200, r.text
    return subsection


def _assign(client, emp_id, subsection_id):
    r = client.post(
        f"/employees/{emp_id}/violations",
        json={"subsection_id": subsection_id}, headers=ACTOR,
    )
    assert r.status_code == 201, r.text
    return r.json()


# ---------------- assign -> remove -> verify audit ----------------
def test_remove_violation_creates_audit_trail(app1_client):
    emp = _emp(app1_client, "W1", first="Wendy", last="Wu")
    subsection = _punishable_subsection(app1_client, _vtype(app1_client, "Late"))

    record = _assign(app1_client, emp["id"], subsection["id"])
    vid = record["id"]

    r = app1_client.post(
        f"/violations/{vid}/remove",
        json={"reason": "Policy amnesty Q4"},
        headers={"X-Actor": "HR-Manager"},
    )
    assert r.status_code == 201
    removal = r.json()
    assert removal["violation_record_id"] == vid
    assert removal["removed_by"] == "HR-Manager"
    assert removal["reason"] == "Policy amnesty Q4"
    assert removal["employee_full_name"] == "Wendy Wu"
    assert removal["penalty_description"] == "Verbal warning"
    assert removal["offense_number"] == 1

    # Original record gone
    assert app1_client.get(f"/violations/{vid}").status_code == 404

    # Removal appears in list
    r = app1_client.get(f"/violation-removals?employee_id={emp['id']}")
    assert r.status_code == 200
    assert r.json()["total"] == 1

    # Active count resets; the offense stays in all-time history
    r = app1_client.get(f"/employees/{emp['id']}/totals")
    assert r.json()["active_violation_count"] == 0
    assert r.json()["total_offenses"] == 1


def test_clear_employee_violations_removes_all(app1_client):
    emp = _emp(app1_client, "W2")
    subsection = _punishable_subsection(app1_client, _vtype(app1_client, "Late"))
    for _ in range(3):
        _assign(app1_client, emp["id"], subsection["id"])

    r = app1_client.post(
        f"/employees/{emp['id']}/violations/clear",
        json={"reason": "Clean slate"}, headers=ACTOR,
    )
    assert r.status_code == 200
    assert r.json()["deleted"] == 3

    r = app1_client.get(f"/employees/{emp['id']}/violations")
    assert r.json() == []

    r = app1_client.get(f"/violation-removals?employee_id={emp['id']}")
    assert r.json()["total"] == 3


# ---------------- audit log survives hard delete ----------------

def test_activity_survives_hard_delete(app1_client):
    emp = _emp(app1_client, "SURV")
    app1_client.delete(f"/employees/{emp['id']}", headers=ACTOR)

    r = app1_client.get("/activity/timeline?action=employee.deleted")
    body = r.json()
    assert body["total"] == 1
    assert body["items"][0]["employee_id"] == emp["id"]


def test_hard_delete_erases_employee_violations_and_removals(app1_client):
    emp = _emp(app1_client, "ERASE")
    subsection = _punishable_subsection(app1_client, _vtype(app1_client, "Erase"))
    _assign(app1_client, emp["id"], subsection["id"])
    removed = _assign(app1_client, emp["id"], subsection["id"])
    r = app1_client.post(
        f"/violations/{removed['id']}/remove",
        json={"reason": "Before erasure"}, headers=ACTOR)
    assert r.status_code == 201

    r = app1_client.delete(f"/employees/{emp['id']}", headers=ACTOR)
    assert r.status_code == 204

    assert app1_client.get(f"/employees/{emp['id']}").status_code == 404
    assert app1_client.get(
        f"/violation-removals?employee_id={emp['id']}").json()["total"] == 0


# ---------------- bulk create ----------------

def test_bulk_create_employees(app1_client):
    r = app1_client.post("/employees/bulk", json=[
        {"employee_code": "BULK1", "first_name": "A", "last_name": "One"},
        {"employee_code": "BULK2", "first_name": "B", "last_name": "Two"},
        {"employee_code": "BULK3", "first_name": "C", "last_name": "Three"},
    ], headers=ACTOR)
    assert r.status_code == 201
    body = r.json()
    assert body["created"] == 3
    assert {e["employee_code"] for e in body["employees"]} == {"BULK1", "BULK2", "BULK3"}


# ---------------- analytics with real data ----------------
def test_top_offenders_ordering(app1_client):
    a = _emp(app1_client, "TO_A", first="A", last="A")
    b = _emp(app1_client, "TO_B", first="B", last="B")
    subsection = _punishable_subsection(app1_client, _vtype(app1_client, "V"))
    for _ in range(2):
        _assign(app1_client, a["id"], subsection["id"])
    _assign(app1_client, b["id"], subsection["id"])

    r = app1_client.get("/analytics/top-offenders?by=active")
    codes = [e["employee_code"] for e in r.json()]
    assert codes[0] == "TO_A"      # 2 active violations
    assert codes[1] == "TO_B"      # 1 active violation


def test_watchlist_returns_repeat_strikers(app1_client):
    a = _emp(app1_client, "WL_A", first="A", last="A")
    subsection = _punishable_subsection(app1_client, _vtype(app1_client, "Strike"))
    for _ in range(3):
        _assign(app1_client, a["id"], subsection["id"])

    r = app1_client.get("/analytics/watchlist?min_offense_number=2")
    assert r.status_code == 200
    body = r.json()
    assert len(body) == 1
    assert body[0]["employee_code"] == "WL_A"
    assert body[0]["max_offense"] == 3
    assert body[0]["total_offenses"] == 3


def test_analytics_departments_with_real_data(app1_client):
    a = _emp(app1_client, "DEP_A", first="A", last="A", department="Engineering")
    b = _emp(app1_client, "DEP_B", first="B", last="B", department="Engineering")
    subsection = _punishable_subsection(app1_client, _vtype(app1_client, "V"))
    for _ in range(2):
        _assign(app1_client, a["id"], subsection["id"])
    _assign(app1_client, b["id"], subsection["id"])

    r = app1_client.get("/analytics/departments")
    assert r.status_code == 200
    body = r.json()
    row = next(row for row in body if row["department"] == "Engineering")
    assert row["employees"] == 2
    assert row["active_violations"] == 3
