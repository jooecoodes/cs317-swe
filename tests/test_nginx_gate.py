"""
Tier-2: exercises the real nginx/nginx.conf with stub auth + stub apps.
Proves auth-gate behavior at the HTTP layer.
"""
import subprocess
import time

import httpx
import pytest

BASE = "http://localhost:8091"
COMPOSE = "tests/nginx/docker-compose.test.yaml"

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module", autouse=True)
def stack():
    # Clean slate
    subprocess.run(["docker", "compose", "-f", COMPOSE, "down", "-v"], check=False)

    # Build first, separate step — slow on cold cache, fast on subsequent runs.
    # This way `up` returns quickly once containers start.
    subprocess.run(["docker", "compose", "-f", COMPOSE, "build"], check=True)
    subprocess.run(["docker", "compose", "-f", COMPOSE, "up", "-d"], check=True)

    # Readiness: nginx up + auth responding (probe `/`, which triggers _auth).
    # 120 s generous — a truly wedged stack still fails fast enough.
    deadline = time.time() + 120
    last_status = None
    while time.time() < deadline:
        try:
            r = httpx.get(BASE + "/auth/login", timeout=5, follow_redirects=False)
            last_status = r.status_code
            # Anything < 500 means nginx is reachable and auth responded.
            if r.status_code < 500:
                break
        except Exception as exc:
            last_status = repr(exc)
        time.sleep(1)
    else:
        print("\n=== docker compose ps ===")
        subprocess.run(["docker", "compose", "-f", COMPOSE, "ps"])
        print("\n=== last 60 log lines ===")
        subprocess.run(
            ["docker", "compose", "-f", COMPOSE, "logs", "--tail=60"],
        )
        print(f"\n=== last poll status: {last_status} ===")
        raise RuntimeError("nginx never came up")

    yield

    subprocess.run(["docker", "compose", "-f", COMPOSE, "down", "-v"], check=False)

def _get(path, **kw):  return httpx.get(f"{BASE}{path}", follow_redirects=False, **kw)
def _post(path, **kw): return httpx.post(f"{BASE}{path}", follow_redirects=False, **kw)


# ---------- blocked without credentials ----------

def test_app1_blocks_unauthenticated():
    assert _get("/app1/employees").status_code == 401


def test_app2_redirects_unauthenticated_to_login():
    """app2 has error_page 401 = @login; app1 and app3 don't."""
    r = _get("/app2/photos")
    assert r.status_code == 302
    assert "/auth/login" in r.headers["location"]


def test_app3_blocks_unauthenticated():
    assert _get("/app3/devices").status_code == 401


def test_root_redirects_unauthenticated():
    r = _get("/")
    assert r.status_code == 302
    assert "/auth/login" in r.headers["location"]


# ---------- cookie session -> X-Actor forwarded to app1/app2 ----------

def test_app1_forwards_x_actor_from_session():
    r = _get("/app1/employees", cookies={"auth_session": "good"})
    assert r.status_code == 200
    body = r.json()
    assert body["x_actor"] == "Test User"
    assert body["x_device"] is None


def test_app2_forwards_x_actor_from_session():
    r = _get("/app2/photos", cookies={"auth_session": "good"})
    assert r.status_code == 200
    assert r.json()["x_actor"] == "Test User"


def test_app1_strips_prefix():
    r = _get("/app1/employees/123", cookies={"auth_session": "good"})
    assert r.json()["path"] == "employees/123"


def test_host_header_is_forwarded_without_port():
    """nginx uses `$host` (not `$http_host`) — port is intentionally dropped.

    Client sends `Host: localhost:8091`; backend sees `Host: localhost`.
    This is standard and safer than `$http_host` (which would forward
    whatever the client claimed verbatim). If the team ever needs the
    port, change nginx.conf to `$http_host` — but nothing in the services
    currently depends on it.
    """
    r = _get("/app1/x", cookies={"auth_session": "good"})
    assert r.json()["host"] == "localhost"


# ---------- device token -> X-Device forwarded to app3 ----------

def test_device_token_posts_to_app3():
    r = _post("/app3/", json={"id": "phone-1", "points": []},
              headers={"Authorization": "Bearer device-good"})
    assert r.status_code == 200
    assert r.json()["x_device"] == "testuser:phone-1"


def test_device_token_blocked_on_get_app3():
    r = _get("/app3/live/x", headers={"Authorization": "Bearer device-good"})
    assert r.status_code == 401


def test_device_token_blocked_on_post_app1():
    r = _post("/app1/employees", json={},
              headers={"Authorization": "Bearer device-good"})
    assert r.status_code == 401


# ---------- the app3 cookie-session gap ----------

def test_app3_cookie_session_behavior_today():
    """CURRENT behavior: cookie sessions CAN POST to /app3/ with empty X-Device.
    This documents the gap. If a fix lands, this test will fail — update it."""
    r = _post("/app3/", json={"id": "any-device", "points": []},
              cookies={"auth_session": "good"})
    assert r.status_code == 200
    assert r.json()["x_device"] in (None, "")


@pytest.mark.xfail(
    reason="KNOWN GAP: cookie session posts to /app3/ reach the app with empty "
           "X-Device, so gps_service device binding is skipped. Fix: either "
           "(a) auth returns X-Device for sessions on /app3/* paths, or "
           "(b) nginx blocks cookie sessions on /app3/, or "
           "(c) gps_service requires non-empty X-Device on POST. "
           "Un-xfail when fixed.",
    strict=True,
)
def test_app3_cookie_session_should_be_blocked():
    r = _post("/app3/", json={"id": "any-device", "points": []},
              cookies={"auth_session": "good"})
    assert r.status_code in (401, 403)


# ---------- internal locations ----------

def test_underscore_auth_is_internal():
    """location = /_auth { internal; } -> external access returns 404."""
    assert _get("/_auth").status_code == 404


def test_auth_verify_blocked_externally():
    """location = /auth/verify { return 404; }"""
    assert _get("/auth/verify").status_code == 404


# ---------- auth endpoints reachable (no auth_request gate) ----------

def test_auth_login_reachable():
    r = _post("/auth/login", data={"username": "x", "password": "y"})
    assert r.status_code != 401
    assert r.status_code < 400


def test_login_rate_limit():
    """rate=10r/m burst=10 nodelay -> 11th rapid POST gets 503.
    Order-sensitive: run this last, it consumes the login budget."""
    statuses = [_post("/auth/login", data={"u": "x", "p": "y"}).status_code
                for _ in range(12)]
    assert 503 in statuses, f"rate limiter never fired: {statuses}"
