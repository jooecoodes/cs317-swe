from fastapi import FastAPI, Form, Depends
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

# 3. Database Dependency for FastAPI
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# 4. The Updated Endpoint
@gps_service.post("/")
async def receive_location(
    id: str = Form(...),
    lat: float = Form(...),
    lon: float = Form(...),
    timestamp: Optional[int] = Form(None),
    db: Session = Depends(get_db)
):
    today = datetime.date.today()
    
    # Clean the new coordinate
    new_point = {"lat": lat, "lon": lon, "ts": timestamp}

    # Search for an existing trail for this supervisor today
    record = db.query(DailyTracking).filter(
        DailyTracking.supervisor_id == id,
        DailyTracking.date == today
    ).first()

    if not record:
        # First ping of the day: create a new array and pack it
        initial_path = [new_point]
        packed_data = msgpack.packb(initial_path)
        new_record = DailyTracking(supervisor_id=id, date=today, path_blob=packed_data)
        db.add(new_record)
        print(f"Created new daily trail for {id}")
    else:
        # Subsequent pings: unpack the blob, add the point, repack it
        path_list = msgpack.unpackb(record.path_blob)
        path_list.append(new_point)
        record.path_blob = msgpack.packb(path_list)
        print(f"Appended point to daily trail for {id}. Total points: {len(path_list)}")

    db.commit()
    return {"status": "saved"}
