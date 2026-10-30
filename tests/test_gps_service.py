"""Tier-1 tests for gps_service (app3)."""
import time


def _batch(device_id, points):
    return {"id": device_id, "points": points}


def test_first_point_saved(gps_client):
    now = int(time.time())
    r = gps_client.post(
        "/", json=_batch("dev-A", [{"lat": 14.5995, "lon": 120.9842, "ts": now - 10}]),
    )
    assert r.status_code == 200
    assert r.json()["status"] == "success"
    assert r.json()["saved"] == 1


def test_live_after_receive(gps_client):
    now = int(time.time())
    gps_client.post(
        "/", json=_batch("dev-B", [{"lat": 14.6, "lon": 120.9, "ts": now - 5}]),
    )
    r = gps_client.get("/live/dev-B")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "online"
    assert body["lat"] == 14.6


def test_live_unknown_device(gps_client):
    r = gps_client.get("/live/nope")
    assert r.status_code == 200
    assert r.json()["status"] == "not_connected"


def test_devices_lists_online(gps_client):
    now = int(time.time())
    gps_client.post(
        "/", json=_batch("dev-C", [{"lat": 14.6, "lon": 120.9, "ts": now - 5}]),
    )
    r = gps_client.get("/devices")
    assert r.status_code == 200
    body = r.json()
    assert body["count"] >= 1
    assert any(d["device_id"] == "dev-C" for d in body["devices"])


def test_route_returns_segments(gps_client):
    now = int(time.time())
    gps_client.post(
        "/", json=_batch("dev-D", [{"lat": 14.6, "lon": 120.9, "ts": now - 5}]),
    )
    r = gps_client.get("/route/dev-D")
    assert r.status_code == 200
    assert isinstance(r.json()["segments"], list)


def test_device_binding_rejects_mismatched_id(gps_client):
    now = int(time.time())
    r = gps_client.post(
        "/",
        json=_batch("wrong-device", [{"lat": 14.6, "lon": 120.9, "ts": now - 5}]),
        headers={"X-Device": "alice:real-device"},
    )
    assert r.status_code == 403
