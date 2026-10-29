import hashlib, hmac, html, os, secrets, sqlite3, time
from contextlib import closing
from pathlib import Path

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response, JSONResponse
from pydantic import BaseModel

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = Path(os.getenv("AUTH_DB_PATH", BASE_DIR / "auth.db"))
PREFIX = "/auth"
COOKIE = "auth_session"
COOKIE_SECURE = os.getenv("AUTH_COOKIE_SECURE", "1") == "1"
SESSION_TTL = 7 * 24 * 3600
# what a device token may do: POST anywhere under /app3/, nothing else
DEVICE_ALLOWED_PREFIX = "/app3/"
DEVICE_ALLOWED_METHOD = "POST"
DEVICE_ALLOWED = {(DEVICE_ALLOWED_METHOD, DEVICE_ALLOWED_PREFIX)}

SCHEMA = """
CREATE TABLE IF NOT EXISTS users(
  id INTEGER PRIMARY KEY, username TEXT UNIQUE NOT NULL,
  password_hash TEXT NOT NULL, created_at INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS sessions(
  token_hash TEXT PRIMARY KEY,
  user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  expires_at INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS devices(
  id INTEGER PRIMARY KEY, name TEXT UNIQUE NOT NULL,
  token_hash TEXT UNIQUE NOT NULL, revoked INTEGER NOT NULL DEFAULT 0,
  created_at INTEGER NOT NULL);
"""


def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


with closing(db()) as _c:
    _c.executescript(SCHEMA)

DEVICE_TTL = 7 * 24 * 3600   # sliding inactivity window
RENEW_AFTER = 24 * 3600      # extend at most once a day

with closing(db()) as _c, _c:
    _c.execute("""CREATE TABLE IF NOT EXISTS trackers(
        id INTEGER PRIMARY KEY, username TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL, disabled INTEGER NOT NULL DEFAULT 0,
        created_at INTEGER NOT NULL)""")
    cols = {r["name"] for r in _c.execute("PRAGMA table_info(devices)")}
    for col in ("tracker_id", "expires_at", "last_used"):
        if col not in cols:
            _c.execute(f"ALTER TABLE devices ADD COLUMN {col} INTEGER")


# ---------- hashing ----------
def hash_password(pw: str) -> str:
    salt = os.urandom(16)
    h = hashlib.scrypt(pw.encode(), salt=salt, n=2**14, r=8, p=1, dklen=32)
    return f"{salt.hex()}${h.hex()}"


def check_password(pw: str, stored: str) -> bool:
    try:
        salt_hex, h_hex = stored.split("$")
        h = hashlib.scrypt(pw.encode(), salt=bytes.fromhex(salt_hex),
                           n=2**14, r=8, p=1, dklen=32)
        return hmac.compare_digest(h, bytes.fromhex(h_hex))
    except ValueError:
        return False


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


DUMMY_HASH = hash_password("dummy")  # keeps timing similar for unknown users


# ---------- helpers ----------
def safe_next(n: str) -> str:
    """Only allow same-site relative redirects."""
    if n and n.startswith("/") and not n.startswith("//") and "\\" not in n:
        return n
    return "/"


def render_login(next_url: str, error: str = "") -> str:
    err = f'<p class="err">{html.escape(error)}</p>' if error else ""
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Sign in</title>
<style>
  body{{margin:0;min-height:100vh;display:grid;place-items:center;background:#0f1115;
       color:#f2f4f8;font-family:system-ui,sans-serif}}
  form{{width:min(340px,90vw);display:flex;flex-direction:column;gap:12px;padding:24px;
       background:#181b22;border:1px solid #262c37;border-radius:16px}}
  h1{{margin:0 0 4px;font-size:1.2rem}}
  input,button{{font:inherit;padding:11px 12px;border-radius:10px;border:1px solid #262c37;
       background:#0f1115;color:inherit}}
  button{{background:#4f8cff;border-color:#4f8cff;color:#fff;font-weight:600;cursor:pointer}}
  .err{{color:#ff6b6b;margin:0;font-size:.85rem}}
</style></head><body>
<form method="post" action="{PREFIX}/login">
  <h1>Sign in</h1>{err}
  <input type="hidden" name="next" value="{html.escape(next_url)}">
  <input name="username" placeholder="Username" autocomplete="username" required autofocus>
  <input name="password" type="password" placeholder="Password"
         autocomplete="current-password" required>
  <button type="submit">Sign in</button>
</form></body></html>"""


# ---------- app ----------
auth_app = FastAPI(title="Auth", docs_url=None, redoc_url=None, openapi_url=None)


@auth_app.get("/login", response_class=HTMLResponse)
def login_page(next: str = "/"):
    return render_login(safe_next(next))


@auth_app.post("/login")
def login(username: str = Form(...), password: str = Form(...),
          next_url: str = Form("/", alias="next")):
    with closing(db()) as c, c:
        row = c.execute("SELECT id, password_hash FROM users WHERE username=?",
                        (username.strip(),)).fetchone()
        ok = check_password(password, row["password_hash"] if row else DUMMY_HASH)
        if not (row and ok):
            return HTMLResponse(render_login(next_url, "Wrong username or password."),
                                status_code=401)
        token = secrets.token_urlsafe(32)
        now = int(time.time())
        c.execute("DELETE FROM sessions WHERE expires_at < ?", (now,))
        c.execute("INSERT INTO sessions VALUES (?,?,?)",
                  (hash_token(token), row["id"], now + SESSION_TTL))
    resp = RedirectResponse(safe_next(next_url), status_code=303)
    resp.set_cookie(COOKIE, token, max_age=SESSION_TTL, httponly=True,
                    secure=COOKIE_SECURE, samesite="lax", path="/")
    return resp


@auth_app.api_route("/logout", methods=["GET", "POST"])
def logout(request: Request):
    token = request.cookies.get(COOKIE)
    if token:
        with closing(db()) as c, c:
            c.execute("DELETE FROM sessions WHERE token_hash=?", (hash_token(token),))
    resp = RedirectResponse(f"{PREFIX}/login", status_code=303)
    resp.delete_cookie(COOKIE, path="/")
    return resp


@auth_app.get("/verify")
def verify(request: Request):
    """Called by nginx (auth_request) before every protected request."""
    method = request.headers.get("x-original-method", "").upper()
    path = request.headers.get("x-original-uri", "").split("?")[0]
    now = int(time.time())
    with closing(db()) as c:
        token = request.cookies.get(COOKIE)
        if token:
            row = c.execute(
                "SELECT u.username FROM sessions s JOIN users u ON u.id=s.user_id "
                "WHERE s.token_hash=? AND s.expires_at>?",
                (hash_token(token), now)).fetchone()
            if row:
                return Response(status_code=200, headers={"X-User": row["username"]})

        bearer = request.headers.get("authorization", "")
        if bearer.lower().startswith("bearer "):
            dev = c.execute(
                "SELECT d.id, d.name, d.last_used FROM devices d "
                "LEFT JOIN trackers t ON t.id = d.tracker_id "
                "WHERE d.token_hash=? AND d.revoked=0 "
                "AND (d.expires_at IS NULL OR d.expires_at>?) "
                "AND (d.tracker_id IS NULL OR t.disabled=0)",
                (hash_token(bearer[7:].strip()), now)).fetchone()
            if dev and (method, path) in DEVICE_ALLOWED:
                if now - (dev["last_used"] or 0) > RENEW_AFTER:
                    with c:
                        c.execute("UPDATE devices SET last_used=?, expires_at=? WHERE id=?",
                                  (now, now + DEVICE_TTL, dev["id"]))
                return Response(status_code=200, headers={"X-Device": dev["name"]})    
    return Response(status_code=401)


# mob device part

class TrackerLogin(BaseModel):
    username: str
    password: str
    device_id: str


@auth_app.post("/device-login")
def device_login(body: TrackerLogin):
    with closing(db()) as c, c:
        row = c.execute(
            "SELECT id, password_hash FROM trackers WHERE username=? AND disabled=0",
            (body.username.strip(),)).fetchone()
        ok = check_password(body.password, row["password_hash"] if row else DUMMY_HASH)
        if not (row and ok):
            return JSONResponse({"detail": "Wrong username or password."}, status_code=401)
        token = secrets.token_urlsafe(32)
        now = int(time.time())
        name = f"{body.username.strip()}:{body.device_id[:64]}"
        c.execute("DELETE FROM devices WHERE name=?", (name,))  # one token per tracker+phone
        c.execute(
            "INSERT INTO devices(name,token_hash,created_at,tracker_id,expires_at,last_used) "
            "VALUES(?,?,?,?,?,?)",
            (name, hash_token(token), now, row["id"], now + DEVICE_TTL, now))
    return {"token": token, "expires_at": now + DEVICE_TTL}


@auth_app.post("/device-logout")
def device_logout(request: Request):
    bearer = request.headers.get("authorization", "")
    if bearer.lower().startswith("bearer "):
        with closing(db()) as c, c:
            c.execute("UPDATE devices SET revoked=1 WHERE token_hash=?",
                      (hash_token(bearer[7:].strip()),))
    return {"status": "ok"}
