from fastapi import FastAPI, Form, Depends
from fastapi.middleware.cors import CORSMiddleware
import msgpack
import datetime
import time
from sqlalchemy import create_engine, Column, Integer, Date, LargeBinary, String
from sqlalchemy.orm import declarative_base, sessionmaker, Session

# 1. Database Setup
engine = create_engine("sqlite:///./tracking.db", connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class DailyTracking(Base):
    __tablename__ = "daily_tracking"
    id = Column(Integer, primary_key=True, index=True)
    device_id = Column(String, index=True) # Updated to device_id
    date = Column(Date, default=datetime.date.today, index=True)
    path_blob = Column(LargeBinary)

# Rebuild tables
Base.metadata.create_all(bind=engine)

gps_service = FastAPI()

# Allow the frontend HTML file to fetch data
gps_service.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# 2. In-Memory Storage
live_devices = {}       # For instant map updates
device_buffers = {}     # For batching database saves by specific device
BUFFER_LIMIT = 5 

# 3. Core Endpoints
@gps_service.post("/")
async def receive_location(
    id: str = Form(...),
    lat: float = Form(...),
    lon: float = Form(...),
    timestamp: int = Form(None),
    db: Session = Depends(get_db)
):
    new_point = {"lat": lat, "lon": lon, "ts": timestamp}
    
    # A. Update live map status instantly (No database needed)
    live_devices[id] = {
        "lat": lat,
        "lon": lon,
        "last_seen": time.time()
    }
    
    # B. Add to this specific device's database buffer
    if id not in device_buffers:
        device_buffers[id] = []
    device_buffers[id].append(new_point)
    
    print(f"Ping received from {id} | Buffer: {len(device_buffers[id])}/{BUFFER_LIMIT}")
    
    # C. Flush to Database only when buffer is full
    if len(device_buffers[id]) >= BUFFER_LIMIT:
        today = datetime.date.today()
        record = db.query(DailyTracking).filter(
            DailyTracking.device_id == id,
            DailyTracking.date == today
        ).first()

        if not record:
            packed_data = msgpack.packb(device_buffers[id])
            new_record = DailyTracking(device_id=id, date=today, path_blob=packed_data)
            db.add(new_record)
        else:
            path_list = msgpack.unpackb(record.path_blob)
            path_list.extend(device_buffers[id])
            record.path_blob = msgpack.packb(path_list)

        db.commit()
        device_buffers[id].clear()
        print(f"Saved {BUFFER_LIMIT} points to database for {id}.")
        
    return {"status": "success"}

@gps_service.get("/live/{device_id}")
async def get_live_location(device_id: str):
    device = live_devices.get(device_id)
    
    if not device:
        return {"status": "not_connected"}
        
    # If no ping in 15 seconds, they went offline
    is_online = (time.time() - device["last_seen"]) < 15
    
    return {
        "status": "online" if is_online else "disconnected",
        "lat": device["lat"],
        "lon": device["lon"]
    }

@gps_service.get("/route/{device_id}")
async def get_route(device_id: str, db: Session = Depends(get_db)):
    today = datetime.date.today()
    record = db.query(DailyTracking).filter(
        DailyTracking.device_id == device_id,
        DailyTracking.date == today
    ).first()
    
    if not record:
        return {"error": "No route found for today"}
        
    path_list = msgpack.unpackb(record.path_blob)
    return {"path": path_list}
