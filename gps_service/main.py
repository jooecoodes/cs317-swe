import math, time, datetime, statistics
import threading

from pathlib import Path
from zoneinfo import ZoneInfo
from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import create_engine, Column, Integer, BigInteger, Float, String, Index, event
from sqlalchemy.orm import declarative_base, sessionmaker

TZ = ZoneInfo("Asia/Manila")

# ---------- Anti-Jitter Settings (Tuned for Real Android GPS) ----------
MAX_ACC = 25          # Reject GPS fixes with accuracy radius worse than 25m
MAX_SPEED = 55        # Reject sudden teleports faster than 55 m/s (~200 km/h)
GAP = 60              # Start a new route segment if offline > 60s
MIN_MOVE = 15         # Stationary deadzone radius (meters) while stopped
BREAKOUT_DIST = 20    # Final confirmation point must be >= 20m from stationary anchor
MOVE_MIN_STEP = 4     # Ignore micro-wobbles (< 4m) even when already in moving state
ACC_MULTIPLIER = 1.8  # Require movement > 1.8x reported GPS error radius
CONFIRM_COUNT = 3     # Consecutive outward points required to unlock movement
MIN_STRAIGHTNESS = 0.75 # Net distance / total path length ratio to reject zig-zag drift
WINDOW_SIZE = 5       # 5-point rolling median filter for smooth real-world paths
MAX_REJECTS = 5       # Consecutive high-speed points required to accept a large jump

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "tracking.db"

# ---------- DB ----------
engine = create_engine(f"sqlite:///{DB_PATH}", connect_args={"check_same_thread": False})

@event.listens_for(engine, "connect")
def wal(conn, _):
    conn.execute("PRAGMA journal_mode=WAL")

SessionLocal = sessionmaker(bind=engine, autoflush=False)
Base = declarative_base()

class TrackPoint(Base):
    __tablename__ = "track_points"
    id = Column(Integer, primary_key=True)
    device_id = Column(String, nullable=False)
    ts = Column(BigInteger, nullable=False)
    lat = Column(Float, nullable=False)
    lon = Column(Float, nullable=False)
    segment = Column(Integer, nullable=False)
    __table_args__ = (Index("ix_device_ts", "device_id", "ts", unique=True),)

Base.metadata.create_all(engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def day_start():
    return int(datetime.datetime.now(TZ).replace(hour=0, minute=0, second=0, microsecond=0).timestamp())

# ---------- App ----------
gps_service = FastAPI()
gps_service.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

state = {}  # device_id -> {lat, lon, ts, seen, seg, rejects, moving, pending, window}
live = {}   # device_id -> {lat, lon, last_seen}

def purge():
    with SessionLocal() as db:
        n = db.query(TrackPoint).filter(TrackPoint.ts < day_start()).delete()
        db.commit()
    if n:
        state.clear()

def purge_loop():
    while True:
        time.sleep(3600)
        purge()

purge()
threading.Thread(target=purge_loop, daemon=True).start()

class Point(BaseModel):
    lat: float
    lon: float
    ts: int
    acc: float | None = None

class Batch(BaseModel):
    id: str
    points: list[Point]

def haversine(a, b, c, d):
    p1, p2 = math.radians(a), math.radians(c)
    h = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(d - b) / 2) ** 2
    return 12742000 * math.asin(math.sqrt(h))

def is_coherent_breakout(anchor_lat, anchor_lon, pts):
    """Verify that pending points move steadily outward in a consistent direction (not indoor zig-zag jitter)."""
    dists = [haversine(anchor_lat, anchor_lon, pt[0], pt[1]) for pt in pts]
    # 1. Must end beyond BREAKOUT_DIST and move progressively further from anchor
    if dists[-1] < BREAKOUT_DIST or not all(dists[i] < dists[i + 1] for i in range(len(dists) - 1)):
        return False
    # 2. Check straightness ratio (net displacement / total path steps)
    step_sum = sum(haversine(pts[i][0], pts[i][1], pts[i + 1][0], pts[i + 1][1]) for i in range(len(pts) - 1))
    if step_sum < 1.0:
        return False
    net_span = haversine(pts[0][0], pts[0][1], pts[-1][0], pts[-1][1])
    return (net_span / step_sum) >= MIN_STRAIGHTNESS

def load_state(db, dev):
    if dev not in state:
        last = db.query(TrackPoint).filter_by(device_id=dev).order_by(TrackPoint.ts.desc()).first()
        state[dev] = {
            "lat": last.lat, "lon": last.lon, "ts": last.ts, "seen": last.ts,
            "seg": last.segment, "rejects": 0, "moving": False,
            "pending": [], "window": [(last.lat, last.lon)]
        } if last else None
    return state[dev]


@gps_service.get("/map")
async def serve_camera_app():
    return FileResponse(BASE_DIR / "map.html")

@gps_service.post("/")
def receive(batch: Batch, db=Depends(get_db)):
    s = load_state(db, batch.id)
    rows = []

    for p in sorted(batch.points, key=lambda p: p.ts):
        if s is not None and p.ts <= s["seen"]:
            continue                                   # duplicate / out of order

        if p.acc is not None and p.acc > MAX_ACC:
            if s is not None:
                s["seen"] = p.ts
            continue                                   # unreliable fix

        if s is None:
            s = {
                "lat": p.lat, "lon": p.lon, "ts": p.ts, "seen": p.ts,
                "seg": 0, "rejects": 0, "moving": False,
                "pending": [], "window": [(p.lat, p.lon)]
            }
            rows.append(TrackPoint(device_id=batch.id, ts=p.ts, lat=p.lat, lon=p.lon, segment=0))
            continue

        gap = p.ts - s["seen"]
        s["seen"] = p.ts
        d = haversine(s["lat"], s["lon"], p.lat, p.lon)
        dt = max(p.ts - s["ts"], 1)

        # 1. Stationary / Jitter check
        jitter_radius = max(MIN_MOVE, (p.acc or 10) * ACC_MULTIPLIER)
        if not s["moving"] and d < jitter_radius:
            s["rejects"] = 0
            s["pending"].clear()
            continue                                   # standing still inside anchor radius

        # If already moving, drop tiny micro-wobbles (< 4m) or switch back to stationary if stopped
        if s["moving"] and d < MOVE_MIN_STEP:
            s["moving"] = False
            s["pending"].clear()
            continue

        # 2. Speed spike / teleport check
        if d / dt > MAX_SPEED and gap <= GAP:
            s["rejects"] += 1
            if s["rejects"] < MAX_REJECTS:
                continue
            s["seg"] += 1
            s["moving"] = True
            s["pending"].clear()
            s["window"].clear()
        elif not s["moving"]:
            # 3. Accumulate points in pending buffer to confirm genuine directional movement
            s["pending"].append((p.lat, p.lon, p.ts))
            if len(s["pending"]) > CONFIRM_COUNT:
                s["pending"].pop(0)
            if len(s["pending"]) < CONFIRM_COUNT:
                continue
            if not is_coherent_breakout(s["lat"], s["lon"], s["pending"]):
                continue
            # Movement confirmed! Clear window and flush pending points cleanly
            s["moving"] = True
            s["window"] = [(s["lat"], s["lon"])]
            pending_pts = list(s["pending"])
            s["pending"].clear()
            for lat_p, lon_p, ts_p in pending_pts:
                s["window"].append((lat_p, lon_p))
                if len(s["window"]) > WINDOW_SIZE:
                    s["window"].pop(0)
                sm_lat = statistics.median(pt[0] for pt in s["window"])
                sm_lon = statistics.median(pt[1] for pt in s["window"])
                s.update(lat=sm_lat, lon=sm_lon, ts=ts_p, seen=ts_p, rejects=0)
                rows.append(TrackPoint(device_id=batch.id, ts=ts_p, lat=sm_lat, lon=sm_lon, segment=s["seg"]))
            continue

        if gap > GAP:
            s["seg"] += 1
            s["window"].clear()

        # 4. Smooth coordinates with a 5-point rolling median
        s["window"].append((p.lat, p.lon))
        if len(s["window"]) > WINDOW_SIZE:
            s["window"].pop(0)
        smooth_lat = statistics.median(pt[0] for pt in s["window"])
        smooth_lon = statistics.median(pt[1] for pt in s["window"])

        s.update(lat=smooth_lat, lon=smooth_lon, ts=p.ts, seen=p.ts, rejects=0)
        rows.append(TrackPoint(device_id=batch.id, ts=p.ts, lat=smooth_lat, lon=smooth_lon, segment=s["seg"]))

    state[batch.id] = s
    if rows:
        db.add_all(rows)
        db.commit()
    if s:
        live[batch.id] = {"lat": s["lat"], "lon": s["lon"], "last_seen": time.time()}
    return {"status": "success", "saved": len(rows)}

@gps_service.get("/live/{dev}")
def get_live(dev: str):
    d = live.get(dev)
    if not d:
        return {"status": "not_connected"}
    online = time.time() - d["last_seen"] < 15
    return {"status": "online" if online else "disconnected", "lat": d["lat"], "lon": d["lon"]}

@gps_service.get("/route/{dev}")
def route(dev: str, db=Depends(get_db)):
    rows = (db.query(TrackPoint)
              .filter(TrackPoint.device_id == dev, TrackPoint.ts >= day_start())
              .order_by(TrackPoint.ts))
    segs = {}
    for r in rows:
        segs.setdefault(r.segment, []).append([r.lat, r.lon])
    return {"segments": list(segs.values())}