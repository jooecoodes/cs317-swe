"""
Extended tests for gps_service — anti-jitter filtering, movement confirmation,
segment rollover, live/devices fields, and endpoint edge cases.

Companion to test_gps_service.py (which keeps the happy paths).
Do not duplicate assertions across the two files.

TUNING SURFACE
    Every geometry, timing, and threshold used below is derived from the
    constants block. Tweak one constant and the whole suite follows.
    These MUST mirror gps_service/main.py.

    If you later lift the service constants into gps_service/config.py,
    replace the constants block with `from gps_service.config import *`
    and delete the block. Same values, one source of truth.

Timing notes:
  * Track ts must be strictly increasing per device (`ts <= seen` is dropped).
  * /route filters by `ts >= day_start()`, so we use near-current timestamps.
  * Live session reset is verified by monkeypatching gps_service.main.time
    rather than sleeping.
"""
import time

import pytest


# ============================================================
# TUNING CONSTANTS — mirror of gps_service/main.py
# ============================================================
MAX_ACC           = 25        # m  — points above this are dropped
MAX_SPEED         = 55        # m/s — speed sanity ceiling
GAP               = 60        # s  — long gap forces a new segment
MIN_MOVE          = 15        # m  — minimum jitter radius floor
BREAKOUT_DIST     = 20        # m  — min displacement to confirm movement
MOVE_MIN_STEP     = 4         # m  — below this while moving => stopped
ACC_MULTIPLIER    = 1.8       # jitter radius = max(MIN_MOVE, acc * this)
CONFIRM_COUNT     = 3         # coherent points needed to confirm movement
MIN_STRAIGHTNESS  = 0.75
WINDOW_SIZE       = 5         # smoothing window (median)
MAX_REJECTS       = 5         # speed-rejects before forced segment bump
ONLINE_SECONDS    = 15        # s  — ping newer than this counts as online

# Accuracy assumed for points that don't send `acc` — matches the default
# used inside receive():  jitter_radius = max(MIN_MOVE, (p.acc or 10) * ACC_MULTIPLIER)
DEFAULT_ACC = 10
JITTER_RADIUS_M = max(MIN_MOVE, DEFAULT_ACC * ACC_MULTIPLIER)


# ============================================================
# DERIVED GEOMETRY — do not tune, computed from the block above
# ============================================================
_M_PER_DEG_LAT = 111_320.0

def _m_to_deg(m: float) -> float:
    return m / _M_PER_DEG_LAT

# A single movement step that satisfies ALL of these at once:
#   * exceeds the jitter radius          (=> registers as motion, not noise)
#   * exceeds MOVE_MIN_STEP              (=> ongoing motion != "stopped")
#   * CONFIRM_COUNT steps clear BREAKOUT_DIST  (=> breakout confirms)
#   * stays under MAX_SPEED at 1 s spacing     (=> not speed-rejected)
STEP_M = max(
    JITTER_RADIUS_M * 1.2,
    MOVE_MIN_STEP * 2.0,
    (BREAKOUT_DIST / max(CONFIRM_COUNT - 1, 1)) * 1.2,
)
assert STEP_M <= MAX_SPEED * 0.9, (
    f"Tuning is inconsistent: derived step STEP_M={STEP_M:.1f} m at 1 s "
    f"spacing exceeds MAX_SPEED*0.9={MAX_SPEED * 0.9:.1f} m/s. "
    f"Lower MIN_MOVE / BREAKOUT_DIST or raise MAX_SPEED / GAP."
)
assert CONFIRM_COUNT >= 2, "CONFIRM_COUNT must be >= 2 for breakout to exist"

STEP_DEG    = _m_to_deg(STEP_M)
JITTER_DEG  = _m_to_deg(JITTER_RADIUS_M * 0.5)   # definitely filtered
BAD_ACC     = MAX_ACC + 25                       # definitely dropped


# ============================================================
# HELPERS
# ============================================================
def _batch(device_id, points):
    return {"id": device_id, "points": points}


def _pt(lat, lon, ts, acc=None):
    p = {"lat": lat, "lon": lon, "ts": ts}
    if acc is not None:
        p["acc"] = acc
    return p


def _base_ts():
    return int(time.time()) - 5


def _moving_points(t, lat0=14.6, lon=120.9):
    """4 points: 1st seeds the device; next CONFIRM_COUNT confirm movement.
    Straight line, 1 s apart, each hop = STEP_M."""
    pts = [_pt(lat0, lon, t)]
    for i in range(1, CONFIRM_COUNT + 1):
        pts.append(_pt(lat0 + STEP_DEG * i, lon, t + i))
    return pts


class _FakeTime:
    """Stand-in for the `time` module. Only `.time()` is used by main.py."""
    def __init__(self, start=1_000_000.0):
        self.now = start

    def time(self):
        return self.now


# ============================================================
# PAYLOAD VALIDATION
# ============================================================
def test_empty_batch_saves_nothing(gps_client):
    r = gps_client.post("/", json=_batch("empty-dev", []))
    assert r.status_code == 200
    assert r.json() == {"status": "success", "saved": 0}


def test_missing_id_returns_422(gps_client):
    r = gps_client.post("/", json={"points": [_pt(14.6, 120.9, _base_ts())]})
    assert r.status_code == 422


def test_missing_points_returns_422(gps_client):
    r = gps_client.post("/", json={"id": "no-points"})
    assert r.status_code == 422


def test_bad_point_type_returns_422(gps_client):
    r = gps_client.post(
        "/",
        json={"id": "bad-types",
              "points": [{"lat": "x", "lon": 120.9, "ts": _base_ts()}]},
    )
    assert r.status_code == 422


# ============================================================
# BATCH SEMANTICS
# ============================================================
def test_multi_point_batch_that_starts_movement_saves_all(gps_client):
    """One batch seeds AND confirms movement in the same call."""
    r = gps_client.post("/", json=_batch("multi-dev", _moving_points(_base_ts())))
    assert r.status_code == 200
    # 1st point saved directly + CONFIRM_COUNT pending saved on confirmation.
    assert r.json()["saved"] == 1 + CONFIRM_COUNT


def test_resend_same_batch_is_idempotent(gps_client):
    t = _base_ts()
    batch = _batch("dup-dev", [_pt(14.6, 120.9, t)])
    assert gps_client.post("/", json=batch).json()["saved"] == 1
    # ts <= seen -> every point skipped.
    assert gps_client.post("/", json=batch).json()["saved"] == 0


def test_out_of_order_batch_points_sorted(gps_client):
    t = _base_ts()
    pts = _moving_points(t)
    scrambled = [pts[0], pts[2], pts[1]] + pts[3:]
    r = gps_client.post("/", json=_batch("ooo-dev", scrambled))
    assert r.status_code == 200
    assert r.json()["saved"] == 1 + CONFIRM_COUNT


# ============================================================
# FILTERING
# ============================================================
def test_high_acc_point_is_dropped(gps_client):
    t = _base_ts()
    gps_client.post("/", json=_batch("acc-dev", [_pt(14.6, 120.9, t)]))
    # Moves a full step but with acc above MAX_ACC -> dropped.
    r = gps_client.post(
        "/", json=_batch("acc-dev",
                         [_pt(14.6 + STEP_DEG, 120.9, t + 1, acc=BAD_ACC)]),
    )
    assert r.json()["saved"] == 0


def test_single_high_acc_first_point_is_not_persisted(gps_client):
    """Even the very first point must pass the accuracy gate."""
    r = gps_client.post(
        "/", json=_batch("acc-first",
                         [_pt(14.6, 120.9, _base_ts(), acc=BAD_ACC)]),
    )
    assert r.json()["saved"] == 0
    assert gps_client.get("/live/acc-first").json()["status"] == "not_connected"


def test_tiny_movement_dropped_as_jitter(gps_client):
    t = _base_ts()
    gps_client.post("/", json=_batch("jit-dev", [_pt(14.6, 120.9, t)]))
    # Hop smaller than the jitter radius -> filtered.
    r = gps_client.post(
        "/", json=_batch("jit-dev", [_pt(14.6 + JITTER_DEG, 120.9, t + 1)]),
    )
    assert r.json()["saved"] == 0


# ============================================================
# MOVEMENT DETECTION & SEGMENTS
# ============================================================
def test_coherent_movement_creates_single_segment(gps_client):
    gps_client.post("/", json=_batch("move-dev", _moving_points(_base_ts())))
    body = gps_client.get("/route/move-dev").json()
    assert len(body["segments"]) == 1


def test_time_gap_creates_new_segment(gps_client):
    t = _base_ts()
    gps_client.post("/", json=_batch("gap-dev", _moving_points(t)))

    # Time gap > GAP, then one more moving point -> new segment.
    r = gps_client.post(
        "/", json=_batch("gap-dev",
                         [_pt(14.6 + STEP_DEG * (CONFIRM_COUNT + 1),
                              120.9, t + GAP + 100)]),
    )
    assert r.json()["saved"] == 1

    body = gps_client.get("/route/gap-dev").json()
    assert len(body["segments"]) == 2


# ============================================================
# DEVICE BINDING
# ============================================================
def test_device_header_without_colon_skips_binding(gps_client):
    """Tokens created via add-device have no `user:` prefix -> no check."""
    r = gps_client.post(
        "/",
        json=_batch("anything", [_pt(14.6, 120.9, _base_ts())]),
        headers={"X-Device": "solo-token"},
    )
    assert r.status_code == 200
    assert r.json()["saved"] == 1


def test_device_header_with_matching_colon_passes(gps_client):
    r = gps_client.post(
        "/",
        json=_batch("dev-Z", [_pt(14.6, 120.9, _base_ts())]),
        headers={"X-Device": "alice:dev-Z"},
    )
    assert r.status_code == 200
    assert r.json()["saved"] == 1


# ============================================================
# LIVE & /devices FIELDS
# ============================================================
def test_devices_reports_tracker_from_header(gps_client):
    gps_client.post(
        "/",
        json=_batch("trk-dev", [_pt(14.6, 120.9, _base_ts())]),
        headers={"X-Device": "alice:trk-dev"},
    )
    row = next(d for d in gps_client.get("/devices").json()["devices"]
               if d["device_id"] == "trk-dev")
    assert row["tracker"] == "alice"
    assert row["status"] == "online"
    assert "accuracy_m" in row
    assert "last_seen_seconds_ago" in row
    assert "online_for_seconds" in row


def test_devices_tracker_is_none_without_header(gps_client):
    gps_client.post("/", json=_batch("no-hdr-dev",
                                     [_pt(14.6, 120.9, _base_ts())]))
    row = next(d for d in gps_client.get("/devices").json()["devices"]
               if d["device_id"] == "no-hdr-dev")
    assert row["tracker"] is None


def test_devices_include_offline_param_accepted(gps_client):
    r = gps_client.get("/devices?include_offline=true")
    assert r.status_code == 200
    assert "devices" in r.json()


def test_devices_accuracy_passed_through(gps_client):
    gps_client.post(
        "/",
        json=_batch("acc-live",
                    [_pt(14.6, 120.9, _base_ts(), acc=DEFAULT_ACC)]),
    )
    row = next(d for d in gps_client.get("/devices").json()["devices"]
               if d["device_id"] == "acc-live")
    assert row["accuracy_m"] == DEFAULT_ACC


# ============================================================
# LIVE SESSION RESET (time monkeypatched, no sleeping)
# ============================================================
def test_first_seen_resets_after_long_gap(gps_client, monkeypatch):
    from gps_service import main as gps_main

    fake = _FakeTime()
    monkeypatch.setattr(gps_main, "time", fake)

    half = max(1, ONLINE_SECONDS // 2)
    t = int(fake.now)
    gps_client.post("/", json=_batch("reset-dev", [_pt(14.6, 120.9, t)]))

    # Within the online window -> session accumulates.
    fake.now += half
    gps_client.post(
        "/",
        json=_batch("reset-dev",
                    [_pt(14.6 + JITTER_DEG, 120.9, t + half)]),
    )
    row = next(d for d in gps_client.get("/devices").json()["devices"]
               if d["device_id"] == "reset-dev")
    assert row["online_for_seconds"] >= half

    # Past ONLINE_SECONDS -> first_seen resets, online_for_seconds collapses.
    fake.now += ONLINE_SECONDS * 5
    gps_client.post(
        "/",
        json=_batch("reset-dev",
                    [_pt(14.6 + JITTER_DEG * 2, 120.9,
                         t + half + ONLINE_SECONDS * 5)]),
    )
    row = next(d for d in gps_client.get("/devices").json()["devices"]
               if d["device_id"] == "reset-dev")
    # Robust check: < half iff reset happened; if reset broke, value would be
    # half + ONLINE_SECONDS*5, which is >> half.
    assert row["online_for_seconds"] < half


def test_live_status_becomes_disconnected_after_timeout(gps_client, monkeypatch):
    from gps_service import main as gps_main

    fake = _FakeTime()
    monkeypatch.setattr(gps_main, "time", fake)

    t = int(fake.now)
    gps_client.post("/", json=_batch("tmo-dev", [_pt(14.6, 120.9, t)]))
    assert gps_client.get("/live/tmo-dev").json()["status"] == "online"

    fake.now += ONLINE_SECONDS * 2
    assert gps_client.get("/live/tmo-dev").json()["status"] == "disconnected"


# ============================================================
# ROUTE
# ============================================================
def test_route_unknown_device_is_empty(gps_client):
    r = gps_client.get("/route/never-seen")
    assert r.status_code == 200
    assert r.json() == {"segments": []}


def test_route_returns_only_saved_points(gps_client):
    t = _base_ts()
    gps_client.post("/", json=_batch("route-dev", [_pt(14.6, 120.9, t)]))
    # Jitter hop -> filtered, not persisted.
    gps_client.post(
        "/", json=_batch("route-dev", [_pt(14.6 + JITTER_DEG, 120.9, t + 1)]),
    )
    body = gps_client.get("/route/route-dev").json()
    assert len(body["segments"]) == 1
    assert len(body["segments"][0]) == 1


# ============================================================
# MISC
# ============================================================
def test_map_route_is_registered(gps_client):
    """/map serves map.html via FileResponse — file presence is a deployment
    concern, not a test concern; we only assert the route exists."""
    paths = {route.path for route in gps_client.app.routes}
    assert "/map" in paths
