import os
import datetime
import shutil
from fastapi import FastAPI, UploadFile, File, Form, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from sqlalchemy import create_engine, Column, Integer, String, DateTime
from sqlalchemy.orm import declarative_base, sessionmaker, Session

# Create the folder for the actual images
os.makedirs("uploads", exist_ok=True)

engine = create_engine("sqlite:///./photos.db", connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class PhotoRecord(Base):
    __tablename__ = "photo_records"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(String, index=True)
    filepath = Column(String)
    timestamp = Column(DateTime, default=datetime.datetime.now)

Base.metadata.create_all(bind=engine)

pt_app = FastAPI()

pt_app.add_middleware(
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

@pt_app.get("/camera")
async def serve_camera_app():
    return FileResponse("camera.html")

@pt_app.post("/upload")
async def upload_photo(
    user_id: str = Form(...), 
    file: UploadFile = File(...), 
    db: Session = Depends(get_db)
):
    # Generate a unique filename using the current time
    timestamp_str = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_filename = f"{user_id}_{timestamp_str}.jpg"
    file_location = f"uploads/{safe_filename}"
    
    # Save the actual file to the hard drive
    with open(file_location, "wb+") as file_object:
        shutil.copyfileobj(file.file, file_object)
        
    # Save the path to the database
    new_record = PhotoRecord(user_id=user_id, filepath=file_location)
    db.add(new_record)
    db.commit()
    
    return {"status": "success", "file": file_location}
