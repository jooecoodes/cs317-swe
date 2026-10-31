"""
Multi-step integration flows for app1. Each test exercises a sequence
of API calls and verifies state at the end — this is where audit-log
and cascade behavior live.
"""
ACTOR = {"X-Actor": "test"}


def _emp(client, code, first="Alice", last="Smith"):
    r = client.post("/employees", json={
        "employee_code": code, "first_name": first, "last_name": last,
    }, headers=ACTOR)
    assert r.status_code == 201, r.text
    return r.json()


def _vtype(client, name, points=0, strike=False):
    r = client.post("/violation-types", json={
        "name": name, "default_points": points, "is_strike": strike,
    }, headers=ACTOR)
    assert r.status_code == 201, r.text
    return r.json()


# ---------------- assign -> remove -> verify audit ----------------

def test_remove_violation_creates_audit_trail(app1_client):
    emp = _emp(app1_client, "W1", first="Wendy", last="Wu")
    vt = _vtype(app1_client, "Late", points=5, strike=True)

    r = app1_client.post(f"/employees/{emp['id']}/violations",
                         json={"violation_type_id": vt["id"]}, headers=ACTOR)
    vid = r.json()["id"]

    r = app1_client.post(f"/violations/{vid}/remove", json={
        "removed_by": "HR-Manager",
        "reason": "Policy amnesty Q4",
    })
    assert r.status_code == 201
    removal = r.json()
    assert removal["violation_record_id"] == vid
    assert removal["removed_by"] == "HR-Manager"
    assert removal["reason"] == "Policy amnesty Q4"
    assert removal["employee_full_name"] == "Wendy Wu"
    assert removal["points"] == 5
    assert removal["is_strike"] is True

    # Original record gone
    assert app1_client.get(f"/violations/{vid}").status_code == 404

    # Removal appears in list
    r = app1_client.get(f"/violation-removals?employee_id={emp['id']}")
    assert r.status_code == 200
    assert r.json()["total"] == 1

    # Totals reset
    r = app1_client.get(f"/employees/{emp['id']}/totals")
    assert r.json()["total_points"] == 0
    assert r.json()["total_strikes"] == 0
    assert r.json()["total_records"] == 0


def test_clear_employee_violations_removes_all(app1_client):
    emp = _emp(app1_client, "W2")
    vt = _vtype(app1_client, "Late", points=3)
    for _ in range(3):
        app1_client.post(f"/employees/{emp['id']}/violations",
                         json={"violation_type_id": vt["id"]}, headers=ACTOR)

    r = app1_client.post(f"/employees/{emp['id']}/violations/clear", json={
        "removed_by": "Director", "reason": "Clean slate",
    })
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
    vt = _vtype(app1_client, "V", points=5)
    for _ in range(2):
        app1_client.post(f"/employees/{a['id']}/violations",
                         json={"violation_type_id": vt["id"]}, headers=ACTOR)
    app1_client.post(f"/employees/{b['id']}/violations",
                     json={"violation_type_id": vt["id"]}, headers=ACTOR)

    r = app1_client.get("/analytics/top-offenders?by=points")
    codes = [e["employee_code"] for e in r.json()]
    assert codes[0] == "TO_A"      # 10 pts
    assert codes[1] == "TO_B"      # 5 pts


def test_watchlist_returns_repeat_strikers(app1_client):
    a = _emp(app1_client, "WL_A", first="A", last="A")
    vt = _vtype(app1_client, "Strike", strike=True)
    for _ in range(3):
        app1_client.post(f"/employees/{a['id']}/violations",
                         json={"violation_type_id": vt["id"]}, headers=ACTOR)

    r = app1_client.get("/analytics/watchlist?min_strikes=2")
    assert r.status_code == 200
    body = r.json()
    assert len(body) == 1
    assert body[0]["employee_code"] == "WL_A"
    assert body[0]["total_strikes"] == 3


def test_analytics_departments_with_real_data(app1_client):
    a = _emp(app1_client, "DEP_A", first="A", last="A")
    b = _emp(app1_client, "DEP_B", first="B", last="B")
    vt = _vtype(app1_client, "V", points=2, strike=True)
    for _ in range(2):
        app1_client.post(f"/employees/{a['id']}/violations",
                         json={"violation_type_id": vt["id"]}, headers=ACTOR)
    app1_client.post(f"/employees/{b['id']}/violations",
                     json={"violation_type_id": vt["id"]}, headers=ACTOR)

    r = app1_client.get("/analytics/departments")
    assert r.status_code == 200
    body = r.json()
    assert len(body) >= 1
    row = body[0]
    assert row["total_points"] == 6
    assert row["total_records"] == 3
    assert row["total_strikes"] == 3
