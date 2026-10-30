import math, time, datetime, statistics
import threading

from pathlib import Path
from zoneinfo import ZoneInfo
from fastapi import FastAPI, Depends, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import create_engine, Column, Integer, BigInteger, Float, String, Index, event
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import declarative_base, sessionmaker

TZ = ZoneInfo("Asia/Manila")

# ---------- Anti-Jitter Settings (Tuned for Real Android GPS) ----------
MAX_ACC = 25
MAX_SPEED = 55
GAP = 60
MIN_MOVE = 15
BREAKOUT_DIST = 20
MOVE_MIN_STEP = 4
ACC_MULTIPLIER = 1.8
CONFIRM_COUNT = 3
MIN_STRAIGHTNESS = 0.75
WINDOW_SIZE = 5
MAX_REJECTS = 5

ONLINE_SECONDS = 15   # a ping newer than this counts as online

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
live = {}   # device_id -> {lat, lon, last_seen, first_seen, acc, tracker}

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
    dists = [haversine(anchor_lat, anchor_lon, pt[0], pt[1]) for pt in pts]
    if dists[-1] < BREAKOUT_DIST or not all(dists[i] < dists[i + 1] for i in range(len(dists) - 1)):
        return False
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
async def serve_map_app():
    return FileResponse(BASE_DIR / "map.html")

@gps_service.post("/")
def receive(batch: Batch, db=Depends(get_db), x_device: str | None = Header(None)):
    # Device binding: tracker tokens are named "username:device_id". If nginx
    # stamped such a name, the payload id must match it. Tokens without a colon
    # (made with add-device) and requests without the header skip this check.
    if x_device and ":" in x_device and x_device.split(":", 1)[1] != batch.id:
        raise HTTPException(status_code=403, detail="Token does not belong to this device")

    s = load_state(db, batch.id)
    rows = []

    for p in sorted(batch.points, key=lambda p: p.ts):
        if s is not None and p.ts <= s["seen"]:
            continue

        if p.acc is not None and p.acc > MAX_ACC:
            if s is not None:
                s["seen"] = p.ts
            continue

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

        jitter_radius = max(MIN_MOVE, (p.acc or 10) * ACC_MULTIPLIER)
        if not s["moving"] and d < jitter_radius:
            s["rejects"] = 0
            s["pending"].clear()
            continue

        if s["moving"] and d < MOVE_MIN_STEP:
            s["moving"] = False
            s["pending"].clear()
            continue

        if d / dt > MAX_SPEED and gap <= GAP:
            s["rejects"] += 1
            if s["rejects"] < MAX_REJECTS:
                continue
            s["seg"] += 1
            s["moving"] = True
            s["pending"].clear()
            s["window"].clear()
        elif not s["moving"]:
            s["pending"].append((p.lat, p.lon, p.ts))
            if len(s["pending"]) > CONFIRM_COUNT:
                s["pending"].pop(0)
            if len(s["pending"]) < CONFIRM_COUNT:
                continue
            if not is_coherent_breakout(s["lat"], s["lon"], s["pending"]):
                continue
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

        s["window"].append((p.lat, p.lon))
        if len(s["window"]) > WINDOW_SIZE:
            s["window"].pop(0)
        smooth_lat = statistics.median(pt[0] for pt in s["window"])
        smooth_lon = statistics.median(pt[1] for pt in s["window"])

        s.update(lat=smooth_lat, lon=smooth_lon, ts=p.ts, seen=p.ts, rejects=0)
        rows.append(TrackPoint(device_id=batch.id, ts=p.ts, lat=smooth_lat, lon=smooth_lon, segment=s["seg"]))

    state[batch.id] = s

    if rows:
        try:
            db.add_all(rows)
            db.commit()
        except IntegrityError:          # same batch arrived twice at once
            db.rollback()
            for r in rows:
                try:
                    db.add(TrackPoint(device_id=r.device_id, ts=r.ts, lat=r.lat,
                                      lon=r.lon, segment=r.segment))
                    db.commit()
                except IntegrityError:
                    db.rollback()

    if s:
        now = time.time()
        prev = live.get(batch.id, {})
        last_acc = batch.points[-1].acc if batch.points else prev.get("acc")
        tracker = x_device.split(":", 1)[0] if x_device else prev.get("tracker")
        # a gap since the last ping means a new "online session"
        first_seen = prev.get("first_seen", now)
        if now - prev.get("last_seen", 0) > ONLINE_SECONDS:
            first_seen = now
        live[batch.id] = {"lat": s["lat"], "lon": s["lon"], "last_seen": now,
                          "first_seen": first_seen, "acc": last_acc, "tracker": tracker}
    return {"status": "success", "saved": len(rows)}

@gps_service.get("/live/{dev}")
def get_live(dev: str):
    d = live.get(dev)
    if not d:
        return {"status": "not_connected"}
    online = time.time() - d["last_seen"] < ONLINE_SECONDS
    return {"status": "online" if online else "disconnected", "lat": d["lat"], "lon": d["lon"]}

@gps_service.get("/devices")
def devices(include_offline: bool = False):
    now = time.time()
    out = []
    for dev, d in list(live.items()):
        age = now - d["last_seen"]
        online = age < ONLINE_SECONDS
        if not online and not include_offline:
            continue
        out.append({
            "device_id": dev,
            "tracker": d.get("tracker"),
            "status": "online" if online else "disconnected",
            "lat": d["lat"], "lon": d["lon"],
            "accuracy_m": d.get("acc"),
            "last_seen_seconds_ago": int(age),
            "online_for_seconds": int(d["last_seen"] - d.get("first_seen", d["last_seen"])) if online else 0,
        })
    out.sort(key=lambda x: x["last_seen_seconds_ago"])
    return {"count": len(out), "devices": out}

@gps_service.get("/route/{dev}")
def route(dev: str, db=Depends(get_db)):
    rows = (db.query(TrackPoint)
              .filter(TrackPoint.device_id == dev, TrackPoint.ts >= day_start())
              .order_by(TrackPoint.ts))
    segs = {}
    for r in rows:
        segs.setdefault(r.segment, []).append([r.lat, r.lon])
    return {"segments": list(segs.values())}
