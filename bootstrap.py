from sqlalchemy import select
from models import Base, ViolationType        # ← importing models registers the tables
from db import engine, SessionLocal


DEFAULT_VIOLATION_TYPES = [
    # (name, description, default_points, is_strike)
    ("Late",            "Arrived late to shift",                  1, False),
    ("Insubordination", "Refused to follow a lawful instruction",  5, True),
    ("Safety Violation","Broke a safety rule",                    3, False),
]


def init_db() -> None:
    """Create all tables in data/app.db if they don't exist."""
    Base.metadata.create_all(engine)


def seed_violation_types() -> None:
    """Insert default rulebook entries. Idempotent — safe to run repeatedly."""
    with SessionLocal() as session:
        existing = {
            name for (name,) in session.execute(select(ViolationType.name))
        }
        for name, desc, pts, strike in DEFAULT_VIOLATION_TYPES:
            if name not in existing:
                session.add(ViolationType(
                    name=name,
                    description=desc,
                    default_points=pts,
                    is_strike=strike,
                    is_active=True,
                ))
        session.commit()


def bootstrap() -> None:
    """Full orchestration: DB file → tables → seed."""
    init_db()
    seed_violation_types()
