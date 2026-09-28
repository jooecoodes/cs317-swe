from fastapi import FastAPI, Form, Depends
from fastapi.middleware.cors import CORSMiddleware
from typing import Optional
import msgpack
import datetime
from sqlalchemy import create_engine, Column, Integer, Date, LargeBinary, String
from sqlalchemy.orm import declarative_base, sessionmaker, Session


# 1. Database Setup
engine = create_engine("sqlite:///./tracking.db", connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# 2. Table Schema
class DailyTracking(Base):
    __tablename__ = "daily_tracking"
    id = Column(Integer, primary_key=True, index=True)
    supervisor_id = Column(String, index=True) # Using the Traccar ID string
    date = Column(Date, default=datetime.date.today, index=True)
    path_blob = Column(LargeBinary) # The binary column for MessagePack

# Create the tables in the database
Base.metadata.create_all(bind=engine)

gps_service = FastAPI()

# websocket connection manager
class ConnectionManager: 
    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)

    async def broadcast(self, message: dict):
        for connection in self.active_connections:
            await connection.send_json(message)

manager = ConnectionManager()

# temporary RAM buffer
point_buffer = []
BUFFER_LIMIT = 5 # Condition: Save to DB every 5 pings

# Cors set up
gps_service.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # Allows local HTML file to fetch data
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 3. Database Dependency for FastAPI
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Live Tunnel Endpoint
@gps_service.websocket("/ws/live")
async def live_tracking(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            # Keeps the tunnel open waiting for client disconnects
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)

@gps_service.post("/")
async def receive_location(
    id: str = Form(...),
    lat: float = Form(...),
    lon: float = Form(...),
    timestamp: int = Form(None),
    db: Session = Depends(get_db)
):
    new_point = {"id": id, "lat": lat, "lon": lon, "ts": timestamp}
    
    # ACTION A: Instantly push the live location to the web dashboard (No DB hit)
    await manager.broadcast(new_point)
    
    # ACTION B: Store in RAM buffer
    point_buffer.append(new_point)
    print(f"Live broadcasted! Buffer size: {len(point_buffer)}/{BUFFER_LIMIT}")
    
    # ACTION C: The Condition - Only hit the database if the buffer is full
    if len(point_buffer) >= BUFFER_LIMIT:
        today = datetime.date.today()
        record = db.query(DailyTracking).filter(
            DailyTracking.supervisor_id == id,
            DailyTracking.date == today
        ).first()

        if not record:
            packed_data = msgpack.packb(point_buffer)
            new_record = DailyTracking(supervisor_id=id, date=today, path_blob=packed_data)
            db.add(new_record)
        else:
            path_list = msgpack.unpackb(record.path_blob)
            path_list.extend(point_buffer) # Add all buffered points at once
            record.path_blob = msgpack.packb(path_list)

        db.commit()
        point_buffer.clear()
        print("Buffer full. Performed bulk write to database.")
        
    return {"status": "success"}
@gps_service.get("/route/{supervisor_id}")
async def get_route(supervisor_id: str, db: Session = Depends(get_db)):
    today = datetime.date.today()
    record = db.query(DailyTracking).filter(
        DailyTracking.supervisor_id == supervisor_id,
        DailyTracking.date == today
    ).first()
    
    if not record:
        return {"error": "No route found for today"}
        
    # Unpack the binary blob back into a normal Python dictionary
    path_list = msgpack.unpackb(record.path_blob)
    return {"path": path_list}
