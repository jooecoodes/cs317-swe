"""
Priority-2 tests for pt_service — /rename, /history, /digest, /batch,
/bulk-delete.

Companion to test_pt_service.py (which keeps the happy paths).

TUNING SURFACE
    Values below mirror pt_service/main.py. If you lift the tunables into
    pt_service/config.py later, replace the block with a single import.

    REQUIRE_ACTOR is read at import time in main.py from the env var; the
    conftest does not set it, so it defaults to "1" and thus True. Tests
    that assume the header is required will skip loudly if that changes.

IMPORT RULE (from conftest):
    Never import pt_service.main at module top. Import inside tests /
    fixture bodies so the create_engine patch is already in effect.
"""
import io
from datetime import date, datetime, timedelta

import pytest


# ============================================================
# TUNING CONSTANTS — mirror of pt_service/main.py
# ============================================================
ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".heic"}
MAX_UPLOAD_BYTES   = 15 * 1024 * 1024
MAX_DIGEST_DAYS    = 366
MAX_BATCH_IDS      = 200


# ============================================================
# HELPERS
# ============================================================
def _png_bytes():
    # 1x1 transparent PNG
    return bytes.fromhex(
        "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
        "0000000a49444154789c6300010000050001"
        "0d0a2db40000000049454e44ae426082"
    )


def _upload(client, actor_headers, *, name="test.png", display_name=None,
            tags=None):
    data = {}
    if display_name is not None:
        data["display_name"] = display_name
    if tags is not None:
        data["tags"] = tags
    r = client.post(
        "/upload",
        files={"file": (name, io.BytesIO(_png_bytes()), "image/png")},
        data=data,
        headers=actor_headers,
    )
    assert r.status_code == 201, r.text
    return r.json()


def _upload_dir():
    from pt_service import main as pt_main
    return pt_main.UPLOAD_DIR


# ============================================================
# /photos/{id}/rename
# ============================================================
def test_rename_updates_display_name_only(pt_client, actor_headers):
    up = _upload(pt_client, actor_headers, name="a.png")
    original_filename = up["filename"]

    r = pt_client.post(
        f"/photos/{up['id']}/rename",
        json={"display_name": "New Title", "rename_file": False},
        headers=actor_headers,
    )
    assert r.status_code == 200
    body = r.json()
    assert body["display_name"] == "New Title"
    assert body["filename"] == original_filename
    # File on disk untouched.
    assert (_upload_dir() / original_filename).is_file()


def test_rename_with_rename_file_replaces_on_disk(pt_client, actor_headers):
    up = _upload(pt_client, actor_headers, name="a.png")
    old_name = up["filename"]
    old_path = _upload_dir() / old_name
    assert old_path.is_file()

    r = pt_client.post(
        f"/photos/{up['id']}/rename",
        json={"display_name": "Renamed Photo", "rename_file": True},
        headers=actor_headers,
    )
    assert r.status_code == 200
    new_name = r.json()["filename"]
    assert new_name != old_name

    assert not old_path.is_file(), "old file must be gone after rename_file=True"
    assert (_upload_dir() / new_name).is_file(), "new file must exist on disk"

    # File endpoint still serves the same bytes through the new name.
    r = pt_client.get(f"/photos/{up['id']}/file")
    assert r.status_code == 200
    assert r.content == _png_bytes()


def test_rename_whitespace_only_422(pt_client, actor_headers):
    """RenameRequest allows length >= 1 (Pydantic); route strips and rejects."""
    up = _upload(pt_client, actor_headers)
    r = pt_client.post(
        f"/photos/{up['id']}/rename",
        json={"display_name": "   ", "rename_file": False},
        headers=actor_headers,
    )
    assert r.status_code == 422


def test_rename_empty_string_422_by_pydantic(pt_client, actor_headers):
    up = _upload(pt_client, actor_headers)
    r = pt_client.post(
        f"/photos/{up['id']}/rename",
        json={"display_name": "", "rename_file": False},
        headers=actor_headers,
    )
    assert r.status_code == 422


def test_rename_404_for_missing_photo(pt_client, actor_headers):
    r = pt_client.post(
        "/photos/99999/rename",
        json={"display_name": "x"},
        headers=actor_headers,
    )
    assert r.status_code == 404


def test_rename_creates_activity_entry(pt_client, actor_headers):
    up = _upload(pt_client, actor_headers, display_name="Before")
    pt_client.post(
        f"/photos/{up['id']}/rename",
        json={"display_name": "After", "rename_file": False},
        headers=actor_headers,
    )
    r = pt_client.get(f"/photos/{up['id']}/history", headers=actor_headers)
    actions = [e["action"] for e in r.json()["items"]]
    assert "rename" in actions


# ============================================================
# /photos/{id}/history
# ============================================================
def test_history_returns_upload_and_delete_for_deleted_photo(pt_client, actor_headers):
    up = _upload(pt_client, actor_headers, display_name="Doomed")
    pt_client.delete(f"/photos/{up['id']}", headers=actor_headers)

    r = pt_client.get(f"/photos/{up['id']}/history", headers=actor_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["photo_exists"] is False
    actions = {e["action"] for e in body["items"]}
    assert {"upload", "delete"} <= actions
    # Snapshot display name survives the delete.
    assert body["photo_display_name"] == "Doomed"
    # photo_url hidden on every row because photo is gone.
    for e in body["items"]:
        assert e["photo_url"] is None
        assert e["download_url"] is None


def test_history_for_living_photo_includes_links(pt_client, actor_headers):
    up = _upload(pt_client, actor_headers)
    r = pt_client.get(f"/photos/{up['id']}/history", headers=actor_headers)
    body = r.json()
    assert body["photo_exists"] is True
    upload_row = next(e for e in body["items"] if e["action"] == "upload")
    assert upload_row["photo_url"] == f"/photos/{up['id']}/file"
    assert upload_row["download_url"] == f"/photos/{up['id']}/download"


def test_history_unknown_photo_returns_empty(pt_client, actor_headers):
    r = pt_client.get("/photos/99999/history", headers=actor_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 0
    assert body["items"] == []
    assert body["photo_exists"] is False


def test_history_pagination(pt_client, actor_headers):
    up = _upload(pt_client, actor_headers)
    for i in range(3):
        pt_client.post(
            f"/photos/{up['id']}/rename",
            json={"display_name": f"Round {i}"},
            headers=actor_headers,
        )
    # upload + 3 renames = 4 events
    r = pt_client.get(
        f"/photos/{up['id']}/history?limit=2&offset=0",
        headers=actor_headers,
    )
    body = r.json()
    assert body["total"] == 4
    assert len(body["items"]) == 2

    r = pt_client.get(
        f"/photos/{up['id']}/history?limit=2&offset=2",
        headers=actor_headers,
    )
    assert len(r.json()["items"]) == 2


# ============================================================
# /activity/digest
# ============================================================
def test_digest_default_is_today(pt_client, actor_headers):
    _upload(pt_client, actor_headers)
    r = pt_client.get("/activity/digest", headers=actor_headers)
    assert r.status_code == 200
    body = r.json()
    today = date.today().isoformat()
    assert body["from_date"] == today
    assert body["to_date"] == today
    assert body["total"] >= 1
    assert len(body["days"]) == 1
    assert body["days"][0]["date"] == today


def test_digest_from_date_only_uses_same_date(pt_client, actor_headers):
    _upload(pt_client, actor_headers)
    today = date.today().isoformat()
    r = pt_client.get(
        f"/activity/digest?from_date={today}",
        headers=actor_headers,
    )
    body = r.json()
    assert body["from_date"] == today
    assert body["to_date"] == today


def test_digest_rejects_inverted_range(pt_client, actor_headers):
    today = date.today()
    yesterday = today - timedelta(days=1)
    r = pt_client.get(
        f"/activity/digest?from_date={today.isoformat()}"
        f"&to_date={yesterday.isoformat()}",
        headers=actor_headers,
    )
    assert r.status_code == 422


def test_digest_rejects_range_above_limit(pt_client, actor_headers):
    today = date.today()
    too_far = today - timedelta(days=MAX_DIGEST_DAYS + 1)
    r = pt_client.get(
        f"/activity/digest?from_date={too_far.isoformat()}"
        f"&to_date={today.isoformat()}",
        headers=actor_headers,
    )
    assert r.status_code == 422


def test_digest_yesterday_has_no_activity(pt_client, actor_headers):
    _upload(pt_client, actor_headers)  # activity is today
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    r = pt_client.get(
        f"/activity/digest?from_date={yesterday}&to_date={yesterday}",
        headers=actor_headers,
    )
    body = r.json()
    assert body["total"] == 0
    assert body["days"] == []
    assert "No activity" in body["summary"]


def test_digest_groups_by_actor_within_day(pt_client):
    for actor in ("alice", "bob"):
        pt_client.post(
            "/upload",
            files={"file": (f"{actor}.png", io.BytesIO(_png_bytes()), "image/png")},
            headers={"X-Actor": actor},
        )
    r = pt_client.get("/activity/digest", headers={"X-Actor": "test"})
    body = r.json()
    assert body["total"] == 2

    day = body["days"][0]
    actor_names = {a["actor"] for a in day["actors"]}
    assert actor_names == {"alice", "bob"}
    assert day["highlights"]["distinct_actors"] == 2
    assert day["total"] == 2
    # Per-actor summary exists.
    assert "alice" in day["summary"]
    assert "bob" in day["summary"]


def test_digest_filters_by_actor(pt_client):
    for actor in ("alice", "bob"):
        pt_client.post(
            "/upload",
            files={"file": (f"{actor}.png", io.BytesIO(_png_bytes()), "image/png")},
            headers={"X-Actor": actor},
        )
    r = pt_client.get("/activity/digest?actor=alice", headers={"X-Actor": "test"})
    body = r.json()
    assert body["total"] == 1
    assert {row["actor"] for row in body["totals_by_actor"]} == {"alice"}


def test_digest_q_filter(pt_client):
    pt_client.post(
        "/upload",
        files={"file": ("a.png", io.BytesIO(_png_bytes()), "image/png")},
        headers={"X-Actor": "frank"},
    )
    r = pt_client.get("/activity/digest?q=frank", headers={"X-Actor": "test"})
    body = r.json()
    assert body["total"] == 1
    assert {row["actor"] for row in body["totals_by_actor"]} == {"frank"}


def test_digest_include_items_false_still_reports_counts(pt_client, actor_headers):
    _upload(pt_client, actor_headers)
    _upload(pt_client, actor_headers)
    r = pt_client.get(
        "/activity/digest?include_items=false",
        headers=actor_headers,
    )
    body = r.json()
    assert body["total"] == 2
    for day in body["days"]:
        assert day["items"] == []
        assert day["total"] == 2


def test_digest_groups_across_days(pt_client, actor_headers):
    """Insert raw ActivityLog rows on two different days."""
    from pt_service import main as pt_main

    today = datetime.now()
    yesterday = today - timedelta(days=1)

    with pt_main.SessionLocal() as db:
        db.add(pt_main.ActivityLog(
            actor="test-actor", action="upload",
            photo_display_name="y", created_at=yesterday,
        ))
        db.add(pt_main.ActivityLog(
            actor="test-actor", action="upload",
            photo_display_name="t", created_at=today,
        ))
        db.commit()

    r = pt_client.get(
        f"/activity/digest?from_date={yesterday.date().isoformat()}"
        f"&to_date={today.date().isoformat()}",
        headers=actor_headers,
    )
    body = r.json()
    day_dates = [d["date"] for d in body["days"]]
    assert yesterday.date().isoformat() in day_dates
    assert today.date().isoformat() in day_dates
    assert body["total"] == 2


def test_digest_summary_non_empty_when_activity_exists(pt_client, actor_headers):
    _upload(pt_client, actor_headers)
    r = pt_client.get("/activity/digest", headers=actor_headers)
    assert r.json()["summary"].strip()


# ============================================================
# /photos/batch
# ============================================================
def test_batch_returns_found_and_missing(pt_client, actor_headers):
    a = _upload(pt_client, actor_headers)
    b = _upload(pt_client, actor_headers)

    r = pt_client.post(
        "/photos/batch",
        json={"ids": [a["id"], b["id"], 99999]},
        headers=actor_headers,
    )
    assert r.status_code == 200
    body = r.json()
    assert {p["id"] for p in body["found"]} == {a["id"], b["id"]}
    assert body["missing"] == [99999]


def test_batch_dedupes_ids_preserving_order(pt_client, actor_headers):
    a = _upload(pt_client, actor_headers)
    b = _upload(pt_client, actor_headers)
    r = pt_client.post(
        "/photos/batch",
        json={"ids": [b["id"], a["id"], b["id"], a["id"]]},
        headers=actor_headers,
    )
    ids = [p["id"] for p in r.json()["found"]]
    assert ids == [b["id"], a["id"]]


def test_batch_empty_ids_422(pt_client, actor_headers):
    r = pt_client.post("/photos/batch", json={"ids": []}, headers=actor_headers)
    assert r.status_code == 422


def test_batch_requires_actor(pt_client):
    from pt_service import main as pt_main
    if not pt_main.REQUIRE_ACTOR:
        pytest.skip("REQUIRE_ACTOR=0 in this env")
    r = pt_client.post("/photos/batch", json={"ids": [1]})
    assert r.status_code == 401


# ============================================================
# /photos/bulk-delete
# ============================================================
def test_bulk_delete_multiple(pt_client, actor_headers):
    a = _upload(pt_client, actor_headers)
    b = _upload(pt_client, actor_headers)

    r = pt_client.post(
        "/photos/bulk-delete",
        json={"ids": [a["id"], b["id"]]},
        headers=actor_headers,
    )
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "deleted"
    assert body["deleted"] == 2
    assert body["missing_files"] == []

    # Both records gone.
    assert pt_client.get(f"/photos/{a['id']}").status_code == 404
    assert pt_client.get(f"/photos/{b['id']}").status_code == 404


def test_bulk_delete_ignores_unknown_ids(pt_client, actor_headers):
    a = _upload(pt_client, actor_headers)
    r = pt_client.post(
        "/photos/bulk-delete",
        json={"ids": [a["id"], 99999]},
        headers=actor_headers,
    )
    assert r.status_code == 200
    assert r.json()["deleted"] == 1


def test_bulk_delete_reports_missing_file(pt_client, actor_headers):
    a = _upload(pt_client, actor_headers)
    # Delete the file behind our back — record still exists.
    (_upload_dir() / a["filename"]).unlink()

    r = pt_client.post(
        "/photos/bulk-delete",
        json={"ids": [a["id"]]},
        headers=actor_headers,
    )
    assert r.status_code == 200
    assert len(r.json()["missing_files"]) == 1


def test_bulk_delete_logs_activity_per_photo(pt_client, actor_headers):
    a = _upload(pt_client, actor_headers)
    b = _upload(pt_client, actor_headers)
    pt_client.post(
        "/photos/bulk-delete",
        json={"ids": [a["id"], b["id"]]},
        headers=actor_headers,
    )
    r = pt_client.get("/activity?action=delete", headers=actor_headers)
    deleted_pids = {e["photo_id"] for e in r.json()["items"]}
    assert {a["id"], b["id"]} <= deleted_pids


def test_bulk_delete_empty_ids_422(pt_client, actor_headers):
    r = pt_client.post(
        "/photos/bulk-delete", json={"ids": []}, headers=actor_headers,
    )
    assert r.status_code == 422
