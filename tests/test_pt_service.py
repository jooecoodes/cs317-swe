"""Tier-1 tests for pt_service (app2)."""
import io


def _png_bytes():
    # 1x1 transparent PNG
    return bytes.fromhex(
        "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
        "0000000a49444154789c6300010000050001"
        "0d0a2db40000000049454e44ae426082"
    )


def test_upload_requires_actor(pt_client):
    r = pt_client.post(
        "/upload",
        files={"file": ("a.png", io.BytesIO(_png_bytes()), "image/png")},
    )
    assert r.status_code == 401  # REQUIRE_ACTOR defaults to 1


def test_upload_and_get(pt_client, actor_headers):
    r = pt_client.post(
        "/upload",
        files={"file": ("a.png", io.BytesIO(_png_bytes()), "image/png")},
        data={"display_name": "Test photo"},
        headers=actor_headers,
    )
    assert r.status_code == 201
    body = r.json()
    assert body["owner"] == "test-actor"
    assert body["display_name"] == "Test photo"
    pid = body["id"]

    r = pt_client.get(f"/photos/{pid}")
    assert r.status_code == 200
    assert r.json()["id"] == pid


def test_list_photos(pt_client, actor_headers):
    pt_client.post(
        "/upload",
        files={"file": ("b.png", io.BytesIO(_png_bytes()), "image/png")},
        headers=actor_headers,
    )
    r = pt_client.get("/photos")
    assert r.status_code == 200
    assert r.json()["total"] >= 1


def test_delete_photo(pt_client, actor_headers):
    r = pt_client.post(
        "/upload",
        files={"file": ("c.png", io.BytesIO(_png_bytes()), "image/png")},
        headers=actor_headers,
    )
    pid = r.json()["id"]
    r = pt_client.delete(f"/photos/{pid}", headers=actor_headers)
    assert r.status_code == 200
    assert r.json()["status"] == "deleted"


def test_activity_log_records_upload(pt_client, actor_headers):
    pt_client.post(
        "/upload",
        files={"file": ("d.png", io.BytesIO(_png_bytes()), "image/png")},
        headers=actor_headers,
    )
    r = pt_client.get("/activity", headers=actor_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["total"] >= 1
    assert body["items"][0]["action"] == "upload"
