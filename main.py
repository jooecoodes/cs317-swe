from fastapi import FastAPI, HTTPException, Depends
from sqlalchemy import create_engine, Column, Integer, String, Text, Date, DateTime, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session, relationship
from pydantic import BaseModel
from datetime import date, datetime
from pathlib import Path
from typing import List, Optional   # useful for type hints

# ---------- DATABASE SETUP ----------
BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "data" / "app.db"
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

SQLALCHEMY_DATABASE_URL = f"sqlite:///{DB_PATH}"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False}  # needed for SQLite
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# ---------- SQLALCHEMY MODELS (SCHEMA) ----------
class Employee(Base):
    __tablename__ = "employees"

    id = Column(Integer, primary_key=True, index=True)
    first_name = Column(String, nullable=False)
    last_name = Column(String, nullable=False)
    email = Column(String, unique=True, index=True, nullable=False)
    department = Column(String, nullable=True)
    position = Column(String, nullable=True)
    hire_date = Column(Date, nullable=True)
    status = Column(String, default="Active")  # active, inactive, on leave

    # relationship: one employee can have many violation records
    violation_records = relationship("ViolationRecord", back_populates="employee")


class ViolationType(Base):
    __tablename__ = "violation_types"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, nullable=False)  # e.g., "Tardiness", "Safety Violation"
    description = Column(Text, nullable=True)
    severity = Column(String, default="Medium")  # Low, Medium, High, Critical
    default_penalty = Column(String, nullable=True)  # e.g., "Verbal Warning", "Suspension"

    # relationship: one type can be used in many records
    violation_records = relationship("ViolationRecord", back_populates="violation_type")


class ViolationRecord(Base):
    __tablename__ = "violation_records"

    id = Column(Integer, primary_key=True, index=True)
    employee_id = Column(Integer, ForeignKey("employees.id"), nullable=False)
    violation_type_id = Column(Integer, ForeignKey("violation_types.id"), nullable=False)
    
    date_occurred = Column(Date, nullable=False)
    location = Column(String, nullable=True)
    description = Column(Text, nullable=True)
    reported_by = Column(String, nullable=True)  # name or ID of the supervisor/HR
    status = Column(String, default="Under Review")  # Under Review, Upheld, Dismissed, Appealed
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    employee = relationship("Employee", back_populates="violation_records")
    violation_type = relationship("ViolationType", back_populates="violation_records")


# ---------- CREATE TABLES ON STARTUP ----------
Base.metadata.create_all(bind=engine)


# ---------- FASTAPI APP ----------
app = FastAPI(title="Violation Tracker API")

# dependency to get DB session
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ---------- PYDANTIC SCHEMAS (for request/response validation) ----------
class EmployeeCreate(BaseModel):
    first_name: str
    last_name: str
    email: str
    department: str | None = None
    position: str | None = None

class EmployeeResponse(BaseModel):
    id: int
    first_name: str
    last_name: str
    email: str
    department: str | None = None
    position: str | None = None
    status: str

    class Config:
        from_attributes = True  # Enables ORM to dict conversion


# ---------- PLACEHOLDER ENDPOINTS (to test the DB) ----------
@app.get("/")
def read_root():
    """Log for things if working (debug purposes)"""
    return {"message": "Violation Tracker API is running!"}

@app.post("/employees/", response_model=EmployeeResponse)
def create_employee(employee: EmployeeCreate, db: Session = Depends(get_db)):
    """Add a new employee to the database."""
    existing = db.query(Employee).filter(Employee.email == employee.email).first()
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")
    
    new_employee = Employee(
        first_name=employee.first_name,
        last_name=employee.last_name,
        email=employee.email,
        department=employee.department,
        position=employee.position,
        hire_date=date.today()  # placeholder, you can change this
    )
    db.add(new_employee)
    db.commit()
    db.refresh(new_employee)
    return new_employee

@app.get("/employees/", response_model=list[EmployeeResponse])
def list_employees(db: Session = Depends(get_db)):
    """List all employees (placeholders)."""
    employees = db.query(Employee).all()
    return employees
