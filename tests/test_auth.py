"""Tier-1 tests for the auth service — the gate everything else depends on."""
import os
import secrets
import sqlite3
import time


def test_login_page_renders(auth_client):
    r = auth_client.get("/login")
    assert r.status_code == 200
    assert "<form" in r.text


def test_login_wrong_password_is_401(auth_client, auth_user):
    username, _ = auth_user
    r = auth_client.post(
        "/login",
        data={"username": username, "password": "wrong"},
        follow_redirects=False,
    )
    assert r.status_code == 401


def test_login_then_me(auth_client, auth_user):
    username, password = auth_user
    r = auth_client.post(
        "/login",
        data={"username": username, "password": password},
        follow_redirects=False,
    )
    assert r.status_code == 303
    assert "auth_session" in r.cookies

    r = auth_client.get("/me")
    assert r.status_code == 200
    assert r.json()["username"] == username


def test_verify_blocks_without_credentials(auth_client):
    r = auth_client.get("/verify")
    assert r.status_code == 401


def test_verify_succeeds_with_session(auth_client, auth_user):
    username, password = auth_user
    auth_client.post(
        "/login", data={"username": username, "password": password},
        follow_redirects=False,
    )
    r = auth_client.get(
        "/verify",
        headers={"x-original-method": "GET", "x-original-uri": "/app1/employees"},
    )
    assert r.status_code == 200
    assert r.headers.get("x-username") == username


def test_logout_clears_session(auth_client, auth_user):
    username, password = auth_user
    auth_client.post(
        "/login", data={"username": username, "password": password},
        follow_redirects=False,
    )
    assert auth_client.get("/me").status_code == 200
    auth_client.get("/logout", follow_redirects=False)
    assert auth_client.get("/me").status_code == 401


def test_device_token_scoped_to_post_app3(auth_client):
    """Device tokens may only POST /app3/* — enforced by /verify."""
    from auth.main import hash_password

    trk = f"trk_{secrets.token_hex(4)}"
    pwd = "devicepass"
    with sqlite3.connect(os.environ["AUTH_DB_PATH"]) as c:
        c.execute(
            "INSERT INTO trackers(username, password_hash, created_at) VALUES(?,?,?)",
            (trk, hash_password(pwd), int(time.time())),
        )

    r = auth_client.post(
        "/device-login",
        json={"username": trk, "password": pwd, "device_id": "phone-1"},
    )
    assert r.status_code == 200
    token = r.json()["token"]

    # Allowed: POST /app3/
    r = auth_client.get("/verify", headers={
        "authorization": f"Bearer {token}",
        "x-original-method": "POST",
        "x-original-uri": "/app3/",
    })
    assert r.status_code == 200
    assert r.headers.get("x-device") == f"{trk}:phone-1"

    # Blocked: GET /app3/live/x
    r = auth_client.get("/verify", headers={
        "authorization": f"Bearer {token}",
        "x-original-method": "GET",
        "x-original-uri": "/app3/live/x",
    })
    assert r.status_code == 401

    # Blocked: POST /app1/employees
    r = auth_client.get("/verify", headers={
        "authorization": f"Bearer {token}",
        "x-original-method": "POST",
        "x-original-uri": "/app1/employees",
    })
    assert r.status_code == 401
