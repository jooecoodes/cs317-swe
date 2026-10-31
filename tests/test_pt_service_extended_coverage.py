"""
Extended coverage for pt_service — the remaining untested surface after
Priority-2 (rename/history/digest/batch/bulk-delete):

    * PATCH /photos/{id}            — the edit path w/ diff logging
    * GET   /stats                  — counts, bytes, distinct users
    * GET   /photos                 — owner/q/tag/sort/pagination matrix
    * GET   /photos/{id}/file       — bytes, cache header, 404, 410, traversal
    * GET   /photos/{id}/download   — Content-Disposition, sanitized filename
    * GET   /activity               — filter/pagination matrix
    * GET   /activity/actors        — aggregation, sorting
    * POST  /upload validation      — 415 ext, 415 content-type, 413 size
    * GET   /camera, /ui            — route presence

TUNING SURFACE
    Values mirror pt_service/main.py. If tunables move to pt_service/config.py,
    replace this block with a single import.

IMPORT RULE (from conftest):
    Never import pt_service.main at module top.
"""
import io
from datetime import datetime, timedelta

import pytest


# ============================================================
# TUNING CONSTANTS — mirror of pt_service/main.py
# ============================================================
ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".heic"}
MAX_UPLOAD_BYTES   = 15 * 1024 * 1024


# ============================================================
# HELPERS
# ============================================================
def _png_bytes():
    return bytes.fromhex(
        "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
        "0000000a49444154789c6300010000050001"
        "0d0a2db40000000049454e44ae426082"
    )


def _upload(client, actor_headers, *, name="test.png", display_name=None,
            description=None, tags=None):
    data = {}
    if display_name is not None:
        data["display_name"] = display_name
    if description is not None:
        data["description"] = description
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


def _upload_as(client, actor_name, name="x.png"):
    r = client.post(
        "/upload",
        files={"file": (name, io.BytesIO(_png_bytes()), "image/png")},
        headers={"X-Actor": actor_name},
    )
    assert r.status_code == 201, r.text
    return r.json()


def _upload_dir():
    from pt_service import main as pt_main
    return pt_main.UPLOAD_DIR


def _require_actor_on() -> bool:
    from pt_service import main as pt_main
    return pt_main.REQUIRE_ACTOR


# ============================================================
# PATCH /photos/{id} — the edit path
# ============================================================
def test_patch_display_name_only(pt_client, actor_headers):
    up = _upload(pt_client, actor_headers, display_name="Before")
    r = pt_client.patch(
        f"/photos/{up['id']}",
        json={"display_name": "After"},
        headers=actor_headers,
    )
    assert r.status_code == 200
    assert r.json()["display_name"] == "After"


def test_patch_partial_leaves_other_fields_alone(pt_client, actor_headers):
    up = _upload(
        pt_client, actor_headers,
        display_name="Orig", description="Desc", tags="a,b",
    )
    r = pt_client.patch(
        f"/photos/{up['id']}",
        json={"display_name": "New"},
        headers=actor_headers,
    )
    body = r.json()
    assert body["display_name"] == "New"
    assert body["description"] == "Desc"
    assert body["tags"] == ["a", "b"]


def test_patch_empty_display_name_422(pt_client, actor_headers):
    up = _upload(pt_client, actor_headers)
    r = pt_client.patch(
        f"/photos/{up['id']}",
        json={"display_name": "   "},  # route strips to "" -> 422
        headers=actor_headers,
    )
    assert r.status_code == 422


def test_patch_whitespace_description_becomes_none(pt_client, actor_headers):
    up = _upload(pt_client, actor_headers, description="Original")
    r = pt_client.patch(
        f"/photos/{up['id']}",
        json={"description": "   "},
        headers=actor_headers,
    )
    assert r.status_code == 200
    assert r.json()["description"] is None


def test_patch_tags_dedupes_and_cleans(pt_client, actor_headers):
    up = _upload(pt_client, actor_headers)
    r = pt_client.patch(
        f"/photos/{up['id']}",
        json={"tags": ["a", " b ", "a", "c,d"]},
        headers=actor_headers,
    )
    assert r.status_code == 200
    # "a" deduped; " b " stripped; "c,d" comma -> space (single tag).
    assert r.json()["tags"] == ["a", "b", "c d"]


def test_patch_tags_empty_list_clears(pt_client, actor_headers):
    up = _upload(pt_client, actor_headers, tags="old")
    r = pt_client.patch(
        f"/photos/{up['id']}",
        json={"tags": []},
        headers=actor_headers,
    )
    assert r.status_code == 200
    assert r.json()["tags"] == []


def test_patch_tags_as_string_422(pt_client, actor_headers):
    """Upload takes a comma-string via Form; PATCH requires List[str] via JSON."""
    up = _upload(pt_client, actor_headers)
    r = pt_client.patch(
        f"/photos/{up['id']}",
        json={"tags": "urgent,work"},  # string, not list
        headers=actor_headers,
    )
    assert r.status_code == 422


def test_patch_no_changes_no_edit_log(pt_client, actor_headers):
    """Unchanged payload -> no `edit` activity entry."""
    up = _upload(pt_client, actor_headers, display_name="Same")
    pt_client.patch(
        f"/photos/{up['id']}",
        json={"display_name": "Same"},
        headers=actor_headers,
    )
    r = pt_client.get(f"/photos/{up['id']}/history", headers=actor_headers)
    actions = [e["action"] for e in r.json()["items"]]
    assert "edit" not in actions


def test_patch_logs_edit_with_diff(pt_client, actor_headers):
    up = _upload(pt_client, actor_headers, display_name="Before")
    pt_client.patch(
        f"/photos/{up['id']}",
        json={"display_name": "After", "tags": ["new"]},
        headers=actor_headers,
    )
    r = pt_client.get(f"/photos/{up['id']}/history", headers=actor_headers)
    edit = next(e for e in r.json()["items"] if e["action"] == "edit")
    changes = edit["details"]["changes"]
    assert changes["display_name"]["from"] == "Before"
    assert changes["display_name"]["to"] == "After"
    assert "tags" in changes


def test_patch_404(pt_client, actor_headers):
    r = pt_client.patch(
        "/photos/99999",
        json={"display_name": "X"},
        headers=actor_headers,
    )
    assert r.status_code == 404


def test_patch_requires_actor_before_404(pt_client):
    """Auth dependency resolves before the 404 check."""
    if not _require_actor_on():
        pytest.skip("REQUIRE_ACTOR=0 in this env")
    r = pt_client.patch("/photos/99999", json={"display_name": "X"})
    assert r.status_code == 401


# ============================================================
# GET /stats
# ============================================================
def test_stats_empty(pt_client):
    r = pt_client.get("/stats")
    assert r.status_code == 200
    assert r.json() == {
        "total_photos": 0,
        "total_bytes": 0,
        "total_megabytes": 0.0,
        "distinct_users": 0,
    }


def test_stats_counts_and_bytes(pt_client, actor_headers):
    up1 = _upload(pt_client, actor_headers)
    up2 = _upload(pt_client, actor_headers)
    r = pt_client.get("/stats")
    body = r.json()
    assert body["total_photos"] == 2
    assert body["total_bytes"] == up1["size_bytes"] + up2["size_bytes"]
    assert isinstance(body["total_megabytes"], float)


def test_stats_owner_filter(pt_client):
    _upload_as(pt_client, "alice", "a1.png")
    _upload_as(pt_client, "alice", "a2.png")
    _upload_as(pt_client, "bob", "b1.png")
    r = pt_client.get("/stats?owner=alice")
    assert r.json()["total_photos"] == 2


def test_stats_distinct_users_is_global(pt_client):
    """Quirk: `owner=` filter applies to counts/bytes but NOT to distinct_users."""
    _upload_as(pt_client, "alice", "a1.png")
    _upload_as(pt_client, "bob", "b1.png")
    _upload_as(pt_client, "carol", "c1.png")
    r = pt_client.get("/stats?owner=alice")
    body = r.json()
    assert body["total_photos"] == 1
    assert body["distinct_users"] == 3  # global count — intentional or not


# ============================================================
# GET /photos — filter / sort / paginate
# ============================================================
def test_list_owner_filter(pt_client):
    _upload_as(pt_client, "alice", "a.png")
    _upload_as(pt_client, "bob", "b.png")
    r = pt_client.get("/photos?owner=alice")
    body = r.json()
    assert body["total"] == 1
    assert body["items"][0]["owner"] == "alice"


def test_list_q_search(pt_client, actor_headers):
    _upload(pt_client, actor_headers, name="cat.png",
            display_name="Zebra", description="striped")
    _upload(pt_client, actor_headers, name="dog.png",
            display_name="Apple", description="red")
    _upload(pt_client, actor_headers, name="fish.png",
            display_name="Mango", tags="tropical")

    assert pt_client.get("/photos?q=Zebra").json()["total"] == 1
    assert pt_client.get("/photos?q=red").json()["total"] == 1
    assert pt_client.get("/photos?q=tropical").json()["total"] == 1
    assert pt_client.get("/photos?q=dog").json()["total"] == 1


def test_list_tag_filter(pt_client, actor_headers):
    _upload(pt_client, actor_headers, tags="urgent,work")
    _upload(pt_client, actor_headers, tags="personal")
    r = pt_client.get("/photos?tag=urgent")
    assert r.json()["total"] == 1


def test_list_sort(pt_client, actor_headers):
    _upload(pt_client, actor_headers, display_name="Zebra")
    _upload(pt_client, actor_headers, display_name="Apple")
    _upload(pt_client, actor_headers, display_name="Mango")

    r = pt_client.get("/photos?sort_by=display_name&order=asc")
    names = [p["display_name"] for p in r.json()["items"]]
    assert names == ["Apple", "Mango", "Zebra"]

    r = pt_client.get("/photos?sort_by=display_name&order=desc")
    names = [p["display_name"] for p in r.json()["items"]]
    assert names == ["Zebra", "Mango", "Apple"]


def test_list_pagination(pt_client, actor_headers):
    for i in range(5):
        _upload(pt_client, actor_headers, name=f"p{i}.png")

    r = pt_client.get("/photos?limit=2&offset=0")
    assert len(r.json()["items"]) == 2

    r = pt_client.get("/photos?limit=2&offset=4")
    assert len(r.json()["items"]) == 1  # last page


def test_list_total_ignores_pagination(pt_client, actor_headers):
    for _ in range(5):
        _upload(pt_client, actor_headers)
    r = pt_client.get("/photos?limit=2")
    body = r.json()
    assert body["total"] == 5
    assert len(body["items"]) == 2


# ============================================================
# GET /photos/{id}/file  &  /download
# ============================================================
def test_file_serves_bytes_with_cache_header(pt_client, actor_headers):
    up = _upload(pt_client, actor_headers)
    r = pt_client.get(f"/photos/{up['id']}/file")
    assert r.status_code == 200
    assert r.content == _png_bytes()
    assert r.headers["content-type"].startswith("image/")
    assert "max-age" in r.headers.get("cache-control", "").lower()


def test_file_404(pt_client):
    r = pt_client.get("/photos/99999/file")
    assert r.status_code == 404


def test_file_410_when_missing_on_disk(pt_client, actor_headers):
    up = _upload(pt_client, actor_headers)
    (_upload_dir() / up["filename"]).unlink()
    r = pt_client.get(f"/photos/{up['id']}/file")
    assert r.status_code == 410


def test_file_endpoint_resists_traversal(pt_client):
    """resolve_stored_path uses Path(name).name — any directory parts are stripped."""
    from pt_service import main as pt_main
    with pt_main.SessionLocal() as db:
        photo = pt_main.PhotoRecord(
            owner_name="test-actor",
            filename="../../etc/passwd",
            filepath="uploads/../../etc/passwd",
            original_filename="bad.png",
            content_type="image/png",
            size_bytes=0,
        )
        db.add(photo)
        db.commit()
        pid = photo.id

    r = pt_client.get(f"/photos/{pid}/file")
    # 410 because the sanitized path has no matching file inside uploads/.
    assert r.status_code == 410


def test_download_content_disposition(pt_client, actor_headers):
    up = _upload(pt_client, actor_headers,
                 name="photo.png", display_name="My Nice Photo")
    r = pt_client.get(f"/photos/{up['id']}/download")
    assert r.status_code == 200
    cd = r.headers.get("content-disposition", "").lower()
    assert "attachment" in cd
    assert "my_nice_photo" in cd


def test_download_sanitizes_weird_display_name(pt_client, actor_headers):
    up = _upload(pt_client, actor_headers,
                 display_name="../../etc/passwd")
    r = pt_client.get(f"/photos/{up['id']}/download")
    assert r.status_code == 200
    cd = r.headers.get("content-disposition", "").lower()
    # Dot-slash stripped to underscores by safe_component — no path separators leak.
    assert ".." not in cd
    assert "/" not in cd


# ============================================================
# GET /activity
# ============================================================
def test_activity_actor_filter_case_insensitive(pt_client):
    _upload_as(pt_client, "Alice")
    _upload_as(pt_client, "bob")
    r = pt_client.get("/activity?actor=ALICE", headers={"X-Actor": "test"})
    actors = {e["actor"] for e in r.json()["items"]}
    assert actors == {"Alice"}


def test_activity_action_filter(pt_client, actor_headers):
    up = _upload(pt_client, actor_headers)
    pt_client.patch(
        f"/photos/{up['id']}",
        json={"display_name": "X"},
        headers=actor_headers,
    )
    r = pt_client.get("/activity?action=edit", headers=actor_headers)
    actions = {e["action"] for e in r.json()["items"]}
    assert actions == {"edit"}


def test_activity_photo_id_filter(pt_client, actor_headers):
    up1 = _upload(pt_client, actor_headers)
    _upload(pt_client, actor_headers)
    r = pt_client.get(
        f"/activity?photo_id={up1['id']}", headers=actor_headers,
    )
    pids = {e["photo_id"] for e in r.json()["items"]}
    assert pids == {up1["id"]}


def test_activity_q_matches_details_json(pt_client, actor_headers):
    """`q` also searches the raw details JSON — verify via original_filename."""
    _upload(pt_client, actor_headers, name="unicorn.png",
            display_name="NotUnicorn")
    r = pt_client.get("/activity?q=unicorn", headers=actor_headers)
    # Match comes from details.original_filename, not photo_display_name.
    assert r.json()["total"] >= 1


def test_activity_date_range_filter(pt_client, actor_headers):
    from pt_service import main as pt_main
    today = datetime.now()
    yesterday = today - timedelta(days=1)
    two_days_ago = today - timedelta(days=2)

    with pt_main.SessionLocal() as db:
        for label, when in [
            ("three-days", two_days_ago),
            ("yesterday", yesterday),
            ("today", today),
        ]:
            db.add(pt_main.ActivityLog(
                actor="test-actor", action="upload",
                photo_display_name=label, created_at=when,
            ))
        db.commit()

    r = pt_client.get(
        f"/activity?from_date={yesterday.date().isoformat()}",
        headers=actor_headers,
    )
    names = {e["photo_display_name"] for e in r.json()["items"]}
    assert "three-days" not in names
    assert {"yesterday", "today"} <= names


def test_activity_pagination(pt_client, actor_headers):
    for i in range(5):
        _upload(pt_client, actor_headers, name=f"p{i}.png")
    r1 = pt_client.get("/activity?limit=2&offset=0", headers=actor_headers)
    r2 = pt_client.get("/activity?limit=2&offset=2", headers=actor_headers)
    assert r1.json()["total"] >= 5
    assert len(r1.json()["items"]) == 2
    assert {e["id"] for e in r1.json()["items"]} != {
        e["id"] for e in r2.json()["items"]
    }


def test_activity_requires_actor(pt_client):
    if not _require_actor_on():
        pytest.skip("REQUIRE_ACTOR=0 in this env")
    r = pt_client.get("/activity")
    assert r.status_code == 401


# ============================================================
# GET /activity/actors
# ============================================================
def test_actors_aggregates_per_actor(pt_client):
    _upload_as(pt_client, "alice", "a1.png")
    _upload_as(pt_client, "alice", "a2.png")
    _upload_as(pt_client, "bob", "b1.png")

    r = pt_client.get("/activity/actors", headers={"X-Actor": "test"})
    assert r.status_code == 200
    by_actor = {a["actor"]: a for a in r.json()["actors"]}

    assert by_actor["alice"]["total"] == 2
    assert by_actor["alice"]["actions"]["upload"] == 2
    assert "last_seen" in by_actor["alice"]
    assert by_actor["bob"]["total"] == 1


def test_actors_sorted_by_total_desc(pt_client):
    _upload_as(pt_client, "alice", "a1.png")
    _upload_as(pt_client, "alice", "a2.png")
    _upload_as(pt_client, "bob", "b1.png")
    _upload_as(pt_client, "bob", "b2.png")
    _upload_as(pt_client, "bob", "b3.png")

    r = pt_client.get("/activity/actors", headers={"X-Actor": "test"})
    actors = [a["actor"] for a in r.json()["actors"]]
    # bob(3) before alice(2)
    assert actors.index("bob") < actors.index("alice")


def test_actors_q_filter(pt_client):
    _upload_as(pt_client, "alice", "a.png")
    _upload_as(pt_client, "bob", "b.png")
    r = pt_client.get("/activity/actors?q=ali", headers={"X-Actor": "test"})
    actors = {a["actor"] for a in r.json()["actors"]}
    assert actors == {"alice"}


# ============================================================
# POST /upload — validation
# ============================================================
def test_upload_bad_extension_415(pt_client, actor_headers):
    r = pt_client.post(
        "/upload",
        files={"file": ("evil.exe", io.BytesIO(_png_bytes()), "image/png")},
        headers=actor_headers,
    )
    assert r.status_code == 415


def test_upload_bad_content_type_415(pt_client, actor_headers):
    r = pt_client.post(
        "/upload",
        files={"file": ("a.png", io.BytesIO(_png_bytes()), "text/plain")},
        headers=actor_headers,
    )
    assert r.status_code == 415


def test_upload_oversize_413_and_cleanup(pt_client, actor_headers, monkeypatch):
    from pt_service import main as pt_main
    monkeypatch.setattr(pt_main, "MAX_UPLOAD_BYTES", 100)

    payload = b"x" * 200  # > 100 bytes
    r = pt_client.post(
        "/upload",
        files={"file": ("big.png", io.BytesIO(payload), "image/png")},
        headers=actor_headers,
    )
    assert r.status_code == 413

    # Partial file cleaned up, no DB record created.
    assert list(pt_main.UPLOAD_DIR.iterdir()) == []
    assert pt_client.get("/photos").json()["total"] == 0


# ============================================================
# UI routes
# ============================================================
def test_camera_route_registered(pt_client):
    paths = {route.path for route in pt_client.app.routes}
    assert "/camera" in paths


def test_ui_route_registered(pt_client):
    paths = {route.path for route in pt_client.app.routes}
    assert "/ui" in paths


# ============================================================
# Documented behavior: reads are unauthenticated in standalone
# ============================================================
def test_read_endpoints_are_public_in_standalone(pt_client, actor_headers):
    """Standalone pt_service has NO auth gate on reads.

    In production nginx fronts everything with /verify — this test
    documents the standalone surface so we notice if someone adds
    auth to a read endpoint without updating this file. Flip it
    when we do.
    """
    up = _upload(pt_client, actor_headers)
    for path in (
        "/photos",
        "/stats",
        f"/photos/{up['id']}",
        f"/photos/{up['id']}/file",
        f"/photos/{up['id']}/download",
    ):
        r = pt_client.get(path)
        assert r.status_code != 401, (
            f"{path} unexpectedly requires auth — update this test"
        )
