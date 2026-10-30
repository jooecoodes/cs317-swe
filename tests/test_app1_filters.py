"""
Filter correctness for /employees — including two KNOWN BUGS.

If `test_list_employees_search_total_is_consistent` or
`test_list_employees_department_total_is_consistent` fail, it's because
`count_employees` in queries.py doesn't mirror the filters that
`search_employees` applies. That's a real app bug, not a test bug.
"""
import pytest

ACTOR = {"X-Actor": "test"}


def _emp(client, code, first="Alice", last="Smith", dept=None):
    body = {"employee_code": code, "first_name": first, "last_name": last}
    if dept is not None:
        body["department"] = dept
    r = client.post("/employees", json=body, headers=ACTOR)
    assert r.status_code == 201, r.text
    return r.json()


def _vtype(client, name, points=0, strike=False):
    r = client.post("/violation-types", json={
        "name": name, "default_points": points, "is_strike": strike,
    }, headers=ACTOR)
    assert r.status_code == 201, r.text
    return r.json()


# ---------------- search ----------------

def test_search_by_first_name(app1_client):
    _emp(app1_client, "S1", first="Alice", last="Anderson")
    _emp(app1_client, "S2", first="Bob", last="Brown")
    r = app1_client.get("/employees?search=Alice")
    assert r.status_code == 200
    assert [e["employee_code"] for e in r.json()["items"]] == ["S1"]


def test_search_by_code(app1_client):
    _emp(app1_client, "CODE_X", first="A", last="A")
    _emp(app1_client, "CODE_Y", first="B", last="B")
    r = app1_client.get("/employees?search=CODE_X")
    assert [e["employee_code"] for e in r.json()["items"]] == ["CODE_X"]


# ---------------- KNOWN BUG: total ignores `search` ----------------

@pytest.mark.xfail(
    reason="Bug: count_employees ignores `search` — see app/routers/employees.py line 30. "
           "Un-xfail when queries.count_employees accepts the same filter set.",
    strict=True,
)
def test_list_employees_search_total_is_consistent(app1_client):
    """If 1 employee matches the search, total must be 1.

    Currently FAILS: count_employees doesn't accept `search`, so total
    reflects all employees. Frontend pagination will be wrong.
    """
    _emp(app1_client, "A1", first="Alice", last="Anderson")
    _emp(app1_client, "B1", first="Bob", last="Brown")
    _emp(app1_client, "C1", first="Carol", last="Clark")

    r = app1_client.get("/employees?search=Alice")
    body = r.json()
    assert len(body["items"]) == 1
    assert body["total"] == 1, (
        f"pagination total is wrong: items={len(body['items'])} total={body['total']}"
    )


# ---------------- KNOWN BUG: department substring vs exact ----------------

@pytest.mark.xfail(
    reason="Bug: search_employees uses ilike('%dept%'), count_employees uses ==. "
           "Un-xfail when count_employees matches substring semantics.",
    strict=True,
)
def test_list_employees_department_total_is_consistent(app1_client):
    """If items match `department=Engin` (substring), total must agree.

    Currently FAILS: search_employees uses ilike('%Engin%'), but
    count_employees uses exact equality. So items=1, total=0.
    """
    _emp(app1_client, "D1", dept="Engineering")
    _emp(app1_client, "D2", dept="Sales")

    r = app1_client.get("/employees?department=Engin")
    body = r.json()
    assert len(body["items"]) == 1
    assert body["total"] == 1, (
        f"total disagrees with items: items={len(body['items'])} total={body['total']}"
    )


# ---------------- min_points / min_strikes ----------------

def test_min_points_filter(app1_client):
    a = _emp(app1_client, "MP_A", first="A", last="A")
    b = _emp(app1_client, "MP_B", first="B", last="B")
    vt5 = _vtype(app1_client, "V5", points=5)
    vt10 = _vtype(app1_client, "V10", points=10)
    app1_client.post(f"/employees/{a['id']}/violations",
                     json={"violation_type_id": vt5["id"]}, headers=ACTOR)
    app1_client.post(f"/employees/{b['id']}/violations",
                     json={"violation_type_id": vt10["id"]}, headers=ACTOR)

    r = app1_client.get("/employees?min_points=8")
    codes = [e["employee_code"] for e in r.json()["items"]]
    assert codes == ["MP_B"]


def test_min_strikes_filter(app1_client):
    a = _emp(app1_client, "MS_A", first="A", last="A")
    b = _emp(app1_client, "MS_B", first="B", last="B")
    vt = _vtype(app1_client, "STR", strike=True)
    for _ in range(2):
        app1_client.post(f"/employees/{a['id']}/violations",
                         json={"violation_type_id": vt["id"]}, headers=ACTOR)
    app1_client.post(f"/employees/{b['id']}/violations",
                     json={"violation_type_id": vt["id"]}, headers=ACTOR)

    r = app1_client.get("/employees?min_strikes=2")
    assert [e["employee_code"] for e in r.json()["items"]] == ["MS_A"]


# ---------------- active/inactive ----------------

def test_deactivated_excluded_from_default_search(app1_client):
    emp = _emp(app1_client, "INACT", first="Inactive", last="User")
    app1_client.post(f"/employees/{emp['id']}/deactivate", headers=ACTOR)

    r = app1_client.get("/employees")
    assert "INACT" not in [e["employee_code"] for e in r.json()["items"]]

    r = app1_client.get("/employees?include_inactive=true")
    assert "INACT" in [e["employee_code"] for e in r.json()["items"]]
