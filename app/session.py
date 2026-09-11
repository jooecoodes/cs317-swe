from collections.abc import Generator

from sqlalchemy.orm import Session

from db import SessionLocal  # top-level db.py


def get_session() -> Generator[Session, None, None]:
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
