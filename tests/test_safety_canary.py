# tests/test_safety_canary.py
"""Fails loudly if the temp-DB redirect stops working.

If this test fails, the fixture wipe tests are writing to REAL databases.
Do not merge any change that breaks this test without updating conftest.py.
"""
from pathlib import Path


def test_app1_engine_redirected():
    from db import engine
    url = str(engine.url)
    assert "_TEMP_ROOT" not in url  # sanity: not the raw string
    assert "cs317-tests-" in url, (
        f"app1 engine NOT redirected to temp dir: {url}\n"
        "Fix tests/conftest.py's create_engine patch before proceeding."
    )


def test_pt_engine_redirected():
    from pt_service import main as pt_main
    assert "cs317-tests-" in str(pt_main.engine.url)


def test_gps_engine_redirected():
    from gps_service import main as gps_main
    assert "cs317-tests-" in str(gps_main.engine.url)


def test_auth_db_redirected():
    import os
    assert "cs317-tests-" in os.environ["AUTH_DB_PATH"]
    # And prove auth.main uses it:
    from auth.main import DB_PATH
    assert "cs317-tests-" in str(DB_PATH)


def test_pt_upload_dir_is_temp(pt_client):
    from pt_service import main as pt_main
    assert "cs317-tests-" in str(pt_main.UPLOAD_DIR) or \
           "pytest" in str(pt_main.UPLOAD_DIR), (
        f"UPLOAD_DIR not redirected: {pt_main.UPLOAD_DIR}"
    )
