"""
Tier-1 tests for app1 (Violation Tracker).

Every mutating call sends X-Actor: 'test' — safe whether ActorDep requires
the header or defaults to a fallback. Endpoints tested end-to-end through
the FastAPI layer (no nginx).

Two known-unknowns:
  * Duplicate-code and not-found error codes depend on app/errors.py — those
    tests use a loose `4xx` assertion and will be tightened once we see the
    file.
  * app/deps.py isn't yet in hand; if DbSession bypasses app.db.SessionLocal,
    the conftest redirect will need adjusting (tests will fail loudly).
"""
import time


ACTOR = {"X-Actor": "test"}


# ---------------- helpers ----------------

def _make_employee(client, code="E001", first="Alice", last="Smith", **kw):
    body = {"employee_code": code, "first_name": first, "last_name": last}
    body.update(kw)
    r = client.post("/employees", json=body, headers=ACTOR)
    assert r.status_code == 201, r.text
    return r.json()


def _make_vtype(client, name="Lateness", **kw):
    body = {"name": name}
    body.update(kw)
    r = client.post("/violation-types", json=body, headers=ACTOR)
    assert r.status_code == 201, r.text
    return r.json()


# ---------------- meta ----------------

def test_openapi_served(app1_client):
    r = app1_client.get("/openapi.json")
    assert r.status_code == 200


# ---------------- employees: create / read ----------------

def test_list_employees_empty(app1_client):
    r = app1_client.get("/employees")
    assert r.status_code == 200
    body = r.json()
    assert body["items"] == []
    assert body["total"] == 0


def test_create_employee(app1_client):
    r = app1_client.post("/employees", json={
        "employee_code": "E100",
        "first_name": "Alice",
        "last_name": "Smith",
        "department": "Engineering",
        "position": "Engineer",
    }, headers=ACTOR)
    assert r.status_code == 201
    body = r.json()
    assert body["employee_code"] == "E100"
    assert body["full_name"] == "Alice Smith"
    assert body["status"] == "active"
    assert body["total_points"] == 0
    assert body["total_strikes"] == 0
    assert body["id"] > 0


def test_get_employee_by_id(app1_client):
    emp = _make_employee(app1_client, code="E101", first="Bob", last="Jones")
    r = app1_client.get(f"/employees/{emp['id']}")
    assert r.status_code == 200
    assert r.json()["full_name"] == "Bob Jones"


def test_get_employee_by_code(app1_client):
    _make_employee(app1_client, code="E102", first="Carol", last="Dee")
    r = app1_client.get("/employees/by-code/E102")
    assert r.status_code == 200
    assert r.json()["full_name"] == "Carol Dee"


def test_get_employee_404(app1_client):
    r = app1_client.get("/employees/99999")
    assert r.status_code == 404


def test_get_employee_by_code_404(app1_client):
    r = app1_client.get("/employees/by-code/NOPE")
    assert r.status_code == 404


# ---------------- employees: update / status ----------------

def test_update_employee(app1_client):
    emp = _make_employee(app1_client, code="E200")
    r = app1_client.patch(f"/employees/{emp['id']}", json={
        "department": "Sales",
        "position": "Manager",
    }, headers=ACTOR)
    assert r.status_code == 200
    body = r.json()
    assert body["department"] == "Sales"
    assert body["position"] == "Manager"


def test_deactivate_then_reactivate(app1_client):
    emp = _make_employee(app1_client, code="E201")
    r = app1_client.post(f"/employees/{emp['id']}/deactivate", headers=ACTOR)
    assert r.status_code == 200
    assert r.json()["status"] == "inactive"

    r = app1_client.post(f"/employees/{emp['id']}/reactivate", headers=ACTOR)
    assert r.status_code == 200
    assert r.json()["status"] == "active"


def test_delete_employee(app1_client):
    emp = _make_employee(app1_client, code="E202")
    r = app1_client.delete(f"/employees/{emp['id']}", headers=ACTOR)
    assert r.status_code == 204
    assert app1_client.get(f"/employees/{emp['id']}").status_code == 404


def test_create_duplicate_employee_code(app1_client):
    _make_employee(app1_client, code="DUP1")
    r = app1_client.post("/employees", json={
        "employee_code": "DUP1",
        "first_name": "Bob",
        "last_name": "Jones",
    }, headers=ACTOR)
    assert r.status_code == 409
    assert r.json()["error"] == "DuplicateEmployeeCode"

# ---------------- violation types ----------------

def test_create_violation_type(app1_client):
    r = app1_client.post("/violation-types", json={
        "name": "Unauthorized absence",
        "description": "Missing without notice",
        "default_points": 10,
        "is_strike": True,
    }, headers=ACTOR)
    assert r.status_code == 201
    body = r.json()
    assert body["name"] == "Unauthorized absence"
    assert body["default_points"] == 10
    assert body["is_strike"] is True
    assert body["is_active"] is True


def test_active_violation_types_excludes_inactive(app1_client):
    _make_vtype(app1_client, name="VT-A", is_active=True)
    _make_vtype(app1_client, name="VT-B", is_active=False)
    r = app1_client.get("/violation-types")
    assert r.status_code == 200
    names = [v["name"] for v in r.json()]
    assert "VT-A" in names
    assert "VT-B" not in names


def test_all_violation_types_includes_inactive(app1_client):
    _make_vtype(app1_client, name="VT-C", is_active=True)
    _make_vtype(app1_client, name="VT-D", is_active=False)
    r = app1_client.get("/violation-types/all")
    assert r.status_code == 200
    names = [v["name"] for v in r.json()]
    assert "VT-C" in names
    assert "VT-D" in names


def test_get_violation_type_404(app1_client):
    r = app1_client.get("/violation-types/99999")
    assert r.status_code == 404


def test_deactivate_activate_violation_type(app1_client):
    vt = _make_vtype(app1_client, name="VT-X")
    r = app1_client.post(f"/violation-types/{vt['id']}/deactivate", headers=ACTOR)
    assert r.status_code == 200
    assert r.json()["is_active"] is False

    r = app1_client.post(f"/violation-types/{vt['id']}/activate", headers=ACTOR)
    assert r.status_code == 200
    assert r.json()["is_active"] is True


# ---------------- violations ----------------

def test_assign_violation_snapshots_points(app1_client):
    emp = _make_employee(app1_client, code="E300")
    vt = _make_vtype(app1_client, name="Late", default_points=5, is_strike=True)

    r = app1_client.post(
        f"/employees/{emp['id']}/violations",
        json={"violation_type_id": vt["id"], "notes": "10 min late"},
        headers=ACTOR,
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["employee_id"] == emp["id"]
    assert body["violation_type_id"] == vt["id"]
    assert body["points"] == 5          # snapshotted from vtype
    assert body["is_strike"] is True    # snapshotted from vtype
    assert body["notes"] == "10 min late"


def test_list_employee_violations(app1_client):
    emp = _make_employee(app1_client, code="E301")
    vt = _make_vtype(app1_client, name="Late", default_points=3)
    for _ in range(2):
        app1_client.post(
            f"/employees/{emp['id']}/violations",
            json={"violation_type_id": vt["id"]},
            headers=ACTOR,
        )

    r = app1_client.get(f"/employees/{emp['id']}/violations")
    assert r.status_code == 200
    assert len(r.json()) == 2


def test_employee_totals(app1_client):
    emp = _make_employee(app1_client, code="E302")
    vt = _make_vtype(app1_client, name="Late", default_points=5, is_strike=True)
    app1_client.post(
        f"/employees/{emp['id']}/violations",
        json={"violation_type_id": vt["id"]},
        headers=ACTOR,
    )

    r = app1_client.get(f"/employees/{emp['id']}/totals")
    assert r.status_code == 200
    body = r.json()
    assert body["employee_id"] == emp["id"]
    assert body["total_points"] == 5
    assert body["total_strikes"] == 1
    assert body["total_records"] == 1


def test_employee_detail_includes_violations(app1_client):
    emp = _make_employee(app1_client, code="E303")
    vt = _make_vtype(app1_client, name="Late", default_points=3)
    app1_client.post(
        f"/employees/{emp['id']}/violations",
        json={"violation_type_id": vt["id"]},
        headers=ACTOR,
    )

    r = app1_client.get(f"/employees/{emp['id']}")
    assert r.status_code == 200
    body = r.json()
    assert len(body["violation_records"]) == 1
    assert body["violation_records"][0]["points"] == 3
    assert body["violation_records"][0]["violation_type_name"] == "Late"


def test_recent_violations_feed(app1_client):
    emp = _make_employee(app1_client, code="E304", first="Dan", last="Roe")
    vt = _make_vtype(app1_client, name="Late", default_points=4)
    app1_client.post(
        f"/employees/{emp['id']}/violations",
        json={"violation_type_id": vt["id"]},
        headers=ACTOR,
    )

    r = app1_client.get("/violations/recent")
    assert r.status_code == 200
    body = r.json()
    assert len(body) >= 1
    assert body[0]["employee"]["full_name"] == "Dan Roe"


def test_violation_get_404(app1_client):
    r = app1_client.get("/violations/99999")
    assert r.status_code == 404


# ---------------- activity / analytics ----------------

def test_activity_timeline_empty(app1_client):
    r = app1_client.get("/activity/timeline")
    assert r.status_code == 200
    body = r.json()
    assert body["items"] == []
    assert body["total"] == 0


def test_actor_lands_in_activity_event(app1_client):
    """Integration check: X-Actor -> ActorDep -> ActivityEvent.actor."""
    _make_employee(app1_client, code="E400", first="Eve", last="Park")
    r = app1_client.get("/activity/timeline")
    assert r.status_code == 200
    created = [e for e in r.json()["items"] if e["action"] == "employee.created"]
    assert len(created) >= 1
    assert created[0]["actor"] == "test"


def test_analytics_endpoints_respond_on_empty_db(app1_client):
    for path in (
        "/analytics/top-offenders",
        "/analytics/departments",
        "/analytics/violation-types",
        "/analytics/activity",
        "/analytics/watchlist",
        "/analytics/clean-employees",
    ):
        r = app1_client.get(path)
        assert r.status_code == 200, f"{path}: {r.status_code} {r.text}"
        assert isinstance(r.json(), list), path

def test_delete_violation_type_in_use_returns_409(app1_client):
    """errors.py says ViolationTypeInUse -> 409."""
    emp = _make_employee(app1_client, code="E500")
    vt = _make_vtype(app1_client, name="Locked")
    app1_client.post(
        f"/employees/{emp['id']}/violations",
        json={"violation_type_id": vt["id"]},
        headers=ACTOR,
    )

    r = app1_client.delete(f"/violation-types/{vt['id']}", headers=ACTOR)
    assert r.status_code == 409
    assert r.json()["error"] == "ViolationTypeInUse"

def test_create_employee_requires_actor(app1_client):
    """deps.get_actor raises 400 when X-Actor is missing — documented contract."""
    r = app1_client.post("/employees", json={
        "employee_code": "NOACTOR",
        "first_name": "X",
        "last_name": "Y",
    })
    assert r.status_code == 400
