"""
Test configuration for cs317-swe.

SAFETY: pt_service and gps_service run create_all()/ensure_schema()/purge()
at IMPORT TIME, against hardcoded paths inside the source tree. To keep the
real DBs untouched, we patch sqlalchemy.create_engine BEFORE those modules
are imported — every sqlite:/// URL gets redirected into a temp directory.

RULE: never `from pt_service.main import ...` (or gps_service.main, app.main)
at the top of a test file. Import inside fixtures/tests only.
"""

import os
import secrets
import shutil
import sqlite3
import sys
import tempfile
import time
from pathlib import Path

import pytest

# ---- Step 0: set env vars + redirect sqlite BEFORE any service import ------

_TEMP_ROOT = Path(tempfile.mkdtemp(prefix="cs317-tests-"))

os.environ["AUTH_DB_PATH"] = str(_TEMP_ROOT / "auth.db")
os.environ["AUTH_COOKIE_SECURE"] = "0"   # TestClient serves over http://

import sqlalchemy as _sa

_ORIG_CREATE_ENGINE = _sa.create_engine


def _redirecting_create_engine(url, *args, **kwargs):
    if isinstance(url, str) and url.startswith("sqlite:///"):
        original = url[len("sqlite:///"):]
        name = Path(original).name or "test.db"
        target = _TEMP_ROOT / name
        target.parent.mkdir(parents=True, exist_ok=True)
        return _ORIG_CREATE_ENGINE(f"sqlite:///{target}", *args, **kwargs)
    return _ORIG_CREATE_ENGINE(url, *args, **kwargs)


_sa.create_engine = _redirecting_create_engine

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def pytest_sessionfinish(session, exitstatus):
    shutil.rmtree(_TEMP_ROOT, ignore_errors=True)


# ---- Fixtures --------------------------------------------------------------

@pytest.fixture
def auth_client():
    from fastapi.testclient import TestClient
    from auth.main import auth_app
    with TestClient(auth_app) as c:
        yield c


@pytest.fixture
def auth_user():
    """Insert a unique user directly (no register endpoint exists)."""
    from auth.main import hash_password
    username = f"test_{secrets.token_hex(4)}"
    password = "testpass123"
    with sqlite3.connect(os.environ["AUTH_DB_PATH"]) as c:
        c.execute(
            "INSERT INTO users(username, password_hash, created_at) VALUES(?,?,?)",
            (username, hash_password(password), int(time.time())),
        )
    return username, password


@pytest.fixture
def actor_headers():
    return {"X-Actor": "test-actor"}


@pytest.fixture
def pt_client(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from pt_service import main as pt_main

    uploads = tmp_path / "uploads"
    uploads.mkdir()
    monkeypatch.setattr(pt_main, "UPLOAD_DIR", uploads)

    with pt_main.SessionLocal() as db:
        db.query(pt_main.ActivityLog).delete()
        db.query(pt_main.PhotoRecord).delete()
        db.commit()

    with TestClient(pt_main.pt_app) as c:
        yield c


@pytest.fixture
def gps_client():
    from fastapi.testclient import TestClient
    from gps_service import main as gps_main

    gps_main.state.clear()
    gps_main.live.clear()
    with gps_main.SessionLocal() as db:
        db.query(gps_main.TrackPoint).delete()
        db.commit()

    with TestClient(gps_main.gps_service) as c:
        yield c

@pytest.fixture
def app1_client():
    """Isolated TestClient for app1. Creates schema, wipes tables."""
    from fastapi.testclient import TestClient
    from app.main import app
    from db import SessionLocal, engine          # root-level db.py, not app.db
    from models import (                         # root-level models.py, not app.models
        ActivityEvent,
        Base,
        Employee,
        ViolationRecord,
        ViolationRemoval,
        ViolationType,
    )

    # The app never calls create_all() at import — do it here so the temp
    # DB has schema before any query.
    Base.metadata.create_all(engine)

    with SessionLocal() as db:
        # Order: audit tables first (no FKs), then record → types → employees.
        db.query(ActivityEvent).delete()
        db.query(ViolationRemoval).delete()
        db.query(ViolationRecord).delete()
        db.query(ViolationType).delete()
        db.query(Employee).delete()
        db.commit()

    with TestClient(app) as c:
        yield c
