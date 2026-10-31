"""Pure unit tests for gps_service math — no HTTP, no DB."""
import pytest

from gps_service.main import haversine, is_coherent_breakout


# ---------- haversine ----------

def test_haversine_same_point_is_zero():
    assert haversine(14.6, 120.9, 14.6, 120.9) == 0.0


def test_haversine_one_degree_latitude():
    # 1° of latitude ≈ 111,195 m (Earth R = 6,371 km)
    d = haversine(0.0, 0.0, 1.0, 0.0)
    assert d == pytest.approx(111195, rel=1e-3)


def test_haversine_manila_to_quezon_city():
    # Manila (14.5995, 120.9842) to QC (14.6760, 121.0437) ≈ 11 km
    d = haversine(14.5995, 120.9842, 14.6760, 121.0437)
    assert 10000 < d < 15000


def test_haversine_is_symmetric():
    a = haversine(14.5, 120.9, 14.6, 121.0)
    b = haversine(14.6, 121.0, 14.5, 120.9)
    assert a == pytest.approx(b)


# ---------- is_coherent_breakout ----------

def test_coherent_breakout_rejects_short_distance():
    """BREAKOUT_DIST=20 m; a single 5m step must fail."""
    assert is_coherent_breakout(
        14.6, 120.9, [(14.60005, 120.90000, 0)]
    ) is False


def test_coherent_breakout_rejects_jitter():
    """Random wandering doesn't build net movement in one direction."""
    pts = [
        (14.600005, 120.900005, 0),   # +5m NE
        (14.600000, 120.900000, 1),   # back to origin
        (14.600003, 120.900003, 2),   # +3m NE
    ]
    assert is_coherent_breakout(14.6, 120.9, pts) is False


def test_coherent_breakout_accepts_straight_line():
    """Three points ~10 m apart, straight north — coherent movement."""
    pts = [
        (14.60010, 120.90000, 0),
        (14.60020, 120.90000, 1),
        (14.60030, 120.90000, 2),
    ]
    assert is_coherent_breakout(14.6, 120.9, pts) is True


def test_coherent_breakout_rejects_zigzag():
    """Even with enough distance, back-and-forth fails straightness check."""
    pts = [
        (14.60030, 120.90000, 0),
        (14.60000, 120.90000, 1),
        (14.60030, 120.90000, 2),
    ]
    assert is_coherent_breakout(14.6, 120.9, pts) is False
