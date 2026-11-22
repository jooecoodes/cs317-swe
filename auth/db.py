"""SQLAlchemy engine, session factory, and models for the auth database.

The schema itself is still created and migrated with the existing raw SQLite
DDL in ``auth.main``/``auth.accounts``; this module only maps those tables so
routine CRUD can go through the ORM.
"""
import os
from pathlib import Path

from sqlalchemy import Column, ForeignKey, Index, Integer, String, create_engine, text
from sqlalchemy.orm import declarative_base, sessionmaker

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = Path(os.getenv("AUTH_DB_PATH", BASE_DIR / "auth.db"))
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

engine = create_engine(
    f"sqlite:///{DB_PATH}",
    connect_args={"check_same_thread": False},
    future=True,
)

SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
    expire_on_commit=False,
)

Base = declarative_base()


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    username = Column(String, unique=True, nullable=False)
    password_hash = Column(String, nullable=False)
    created_at = Column(Integer, nullable=False)
    role = Column(String, nullable=False, default="employee", server_default="employee")
    first_name = Column(String)
    last_name = Column(String)
    disabled = Column(Integer, nullable=False, default=0, server_default="0")
    employee_id = Column(Integer)
    employee_code = Column(String)

    __table_args__ = (
        Index(
            "ux_user_employee",
            "employee_id",
            unique=True,
            sqlite_where=text("employee_id IS NOT NULL"),
        ),
    )


class AuthSession(Base):
    __tablename__ = "sessions"

    token_hash = Column(String, primary_key=True)
    user_id = Column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    expires_at = Column(Integer, nullable=False)


class Device(Base):
    __tablename__ = "devices"

    id = Column(Integer, primary_key=True)
    name = Column(String, unique=True, nullable=False)
    token_hash = Column(String, unique=True, nullable=False)
    revoked = Column(Integer, nullable=False, default=0, server_default="0")
    created_at = Column(Integer, nullable=False)
    tracker_id = Column(Integer)
    expires_at = Column(Integer)
    last_used = Column(Integer)


class Tracker(Base):
    __tablename__ = "trackers"

    id = Column(Integer, primary_key=True)
    username = Column(String, unique=True, nullable=False)
    password_hash = Column(String, nullable=False)
    disabled = Column(Integer, nullable=False, default=0, server_default="0")
    created_at = Column(Integer, nullable=False)
    employee_id = Column(Integer)
    employee_code = Column(String)

    __table_args__ = (
        Index(
            "ux_tracker_employee",
            "employee_id",
            unique=True,
            sqlite_where=text("employee_id IS NOT NULL"),
        ),
    )
