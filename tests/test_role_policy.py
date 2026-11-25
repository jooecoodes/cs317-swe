"""Auth gate policy for employee ownership and HR-only tracker access."""
import secrets

import os
import sqlite3

import pytest

from auth import accounts


@pytest.fixture(autouse=True)
def clean_account_store():
    accounts.ensure_schema()
    with sqlite3.connect(os.environ["AUTH_DB_PATH"]) as c:
        for table in ("sessions", "devices", "trackers", "users"):
            c.execute(f"DELETE FROM {table}")
    yield


def _create_employee(client, *, employee_type="employee"):
    suffix = secrets.token_hex(4)
    username = f"user.{suffix}"
    r = client.post("/employees", json={
        "employee_code": f"EMP-{suffix}",
        "first_name": "Casey",
        "last_name": "Tester",
        "employee_type": employee_type,
        "account_username": username,
        "account_password": "verysecret123",
    }, headers={"X-Actor": "hr-tester"})
    assert r.status_code == 201, r.text
    return r.json(), username


def _login(client, username, password="verysecret123"):
    r = client.post("/login", data={"username": username, "password": password},
                    follow_redirects=False)
    assert r.status_code == 303


def _verify(client, method, path):
    return client.get("/verify", headers={
        "x-original-method": method,
        "x-original-uri": path,
        "x-normalized-uri": path,
    })


def test_employee_session_can_only_read_own_history(app1_client, auth_client):
    employee, username = _create_employee(app1_client)
    _login(auth_client, username)

    me = auth_client.get("/me").json()
    assert me["employee_id"] == employee["id"]
    assert me["role"] == "employee"

    assert _verify(auth_client, "GET",
                   f"/app1/employees/{employee['id']}/violation-history").status_code == 200
    assert _verify(auth_client, "GET",
                   f"/app1/employees/{employee['id'] + 1}/violation-history").status_code == 403
    assert _verify(auth_client, "GET", "/app1/employees").status_code == 403
    assert _verify(auth_client, "GET",
                   f"/app1/employees/{employee['id']}/violations").status_code == 403


def test_supervisor_can_read_and_issue_but_not_manage(app1_client, auth_client):
    employee, username = _create_employee(app1_client, employee_type="supervisor")
    _login(auth_client, username)

    assert _verify(auth_client, "GET", "/app1/employees").status_code == 200
    assert _verify(auth_client, "POST",
                   f"/app1/employees/{employee['id']}/violations").status_code == 200
    assert _verify(auth_client, "GET", "/app1/activity/timeline").status_code == 403
    assert _verify(auth_client, "POST", "/app1/employees").status_code == 403
    assert _verify(auth_client, "PATCH",
                   f"/app1/employees/{employee['id']}").status_code == 403


def test_login_password_change_is_hr_only(app1_client, auth_client):
    for role in ("employee", "supervisor", "c_manager"):
        employee, username = _create_employee(
            app1_client, employee_type=role)
        _login(auth_client, username)
        assert auth_client.get(
            f"/employees/{employee['id']}/login-account").status_code == 403
        assert auth_client.patch(
            f"/employees/{employee['id']}/password",
            json={"password": "newsecret123"},
            headers={"X-Requested-With": "Northpoint"}).status_code == 403
        auth_client.cookies.clear()

    employee, username = _create_employee(app1_client, employee_type="employee")
    suffix = secrets.token_hex(4)
    accounts.create_account(
        employee_id=900000 + int(suffix[:4], 16),
        employee_code=f"HR-{suffix}",
        username=f"hr.{suffix}",
        password="verysecret123",
        role="hr",
        first_name="Harriet",
        last_name="Reyes",
    )
    _login(auth_client, f"hr.{suffix}")

    r = auth_client.get(f"/employees/{employee['id']}/login-account")
    assert r.status_code == 200
    assert r.json() == {"username": username, "disabled": False}

    r = auth_client.patch(
        f"/employees/{employee['id']}/password",
        json={"password": "newsecret123"},
        headers={"X-Requested-With": "Northpoint"})
    assert r.status_code == 200, r.text

    auth_client.cookies.clear()
    r = auth_client.post(
        "/login",
        data={"username": username, "password": "verysecret123"},
        follow_redirects=False,
    )
    assert r.status_code == 401
    _login(auth_client, username, "newsecret123")
    assert auth_client.get("/me").json()["employee_id"] == employee["id"]


def test_tracker_access_is_hr_only_and_supervisor_only(
        app1_client, auth_client, monkeypatch):
    from db import engine
    monkeypatch.setenv("APP1_DB_PATH", str(engine.url.database))

    supervisor, supervisor_user = _create_employee(
        app1_client, employee_type="supervisor")
    regular, _ = _create_employee(app1_client, employee_type="employee")

    _login(auth_client, supervisor_user)
    assert auth_client.get(
        f"/employees/{supervisor['id']}/mobile-access").status_code == 403

    suffix = secrets.token_hex(4)
    hr_id = accounts.create_account(
        employee_id=900000 + int(suffix[:4], 16),
        employee_code=f"HR-{suffix}",
        username=f"hr.{suffix}",
        password="verysecret123",
        role="hr",
        first_name="Harriet",
        last_name="Reyes",
    )
    assert hr_id
    auth_client.cookies.clear()
    _login(auth_client, f"hr.{suffix}")

    r = auth_client.get(f"/employees/{supervisor['id']}/mobile-access")
    assert r.status_code == 200
    assert r.json()["eligible"] is True

    r = auth_client.post(
        f"/employees/{supervisor['id']}/mobile-access",
        json={"username": f"tracker.{suffix}", "password": "trackerpass1"},
        headers={"X-Requested-With": "Northpoint"})
    assert r.status_code == 201, r.text

    r = auth_client.post(
        f"/employees/{regular['id']}/mobile-access",
        json={"username": f"tracker2.{suffix}", "password": "trackerpass1"},
        headers={"X-Requested-With": "Northpoint"})
    assert r.status_code == 403
