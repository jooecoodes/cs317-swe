"""Direct account-store helpers shared by the auth service and app1.

The auth service remains the owner of the users table. app1 uses these helpers
when HR creates or edits an employee so the browser login and employee record
stay linked. The store is still SQLite; routine CRUD goes through SQLAlchemy
while the schema DDL remains raw SQLite.
"""
import sqlite3
import time
from contextlib import closing
from pathlib import Path

from sqlalchemy import delete, select, update
from sqlalchemy.exc import IntegrityError

from auth.db import DB_PATH, AuthSession, Device, SessionLocal, Tracker, User
from auth.security import hash_password

ROLES = ("c_manager", "employee", "hr", "supervisor")
_SCHEMA_READY: set[Path] = set()


class AccountError(Exception):
    pass


class UsernameTaken(AccountError):
    pass


class EmployeeAlreadyLinked(AccountError):
    pass


def db_path() -> Path:
    return DB_PATH


def _connect() -> sqlite3.Connection:
    path = db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def ensure_schema() -> None:
    path = db_path().resolve()
    if path in _SCHEMA_READY and path.exists():
        return
    with closing(_connect()) as conn, conn:
        conn.execute("""CREATE TABLE IF NOT EXISTS users(
            id INTEGER PRIMARY KEY, username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL, created_at INTEGER NOT NULL,
            role TEXT NOT NULL DEFAULT 'employee')""")
        conn.execute("""CREATE TABLE IF NOT EXISTS sessions(
            token_hash TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            expires_at INTEGER NOT NULL)""")
        conn.execute("""CREATE TABLE IF NOT EXISTS devices(
            id INTEGER PRIMARY KEY, name TEXT UNIQUE NOT NULL,
            token_hash TEXT UNIQUE NOT NULL, revoked INTEGER NOT NULL DEFAULT 0,
            created_at INTEGER NOT NULL, tracker_id INTEGER,
            expires_at INTEGER, last_used INTEGER)""")
        conn.execute("""CREATE TABLE IF NOT EXISTS trackers(
            id INTEGER PRIMARY KEY, username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL, disabled INTEGER NOT NULL DEFAULT 0,
            created_at INTEGER NOT NULL, employee_id INTEGER,
            employee_code TEXT)""")
        conn.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS ux_tracker_employee "
            "ON trackers(employee_id) WHERE employee_id IS NOT NULL")
        cols = {row["name"] for row in conn.execute("PRAGMA table_info(users)")}
        for name, ddl in (
            ("first_name", "TEXT"),
            ("last_name", "TEXT"),
            ("disabled", "INTEGER NOT NULL DEFAULT 0"),
            ("employee_id", "INTEGER"),
            ("employee_code", "TEXT"),
        ):
            if name not in cols:
                conn.execute(f"ALTER TABLE users ADD COLUMN {name} {ddl}")
        conn.execute(
            "UPDATE users SET role='employee' "
            "WHERE role IS NULL OR role NOT IN (?,?,?,?)", ROLES)
        conn.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS ux_user_employee "
            "ON users(employee_id) WHERE employee_id IS NOT NULL")
    _SCHEMA_READY.add(path)


def create_account(*, employee_id: int, employee_code: str, username: str,
                   password: str, role: str, first_name: str,
                   last_name: str) -> int:
    if role not in ROLES:
        raise AccountError(f"Unknown role: {role}")
    ensure_schema()
    user = User(
        username=username.strip(),
        password_hash=hash_password(password),
        first_name=first_name,
        last_name=last_name,
        created_at=int(time.time()),
        role=role,
        employee_id=employee_id,
        employee_code=employee_code,
    )
    try:
        with SessionLocal() as session:
            session.add(user)
            session.commit()
            return int(user.id)
    except IntegrityError as exc:
        message = str(exc.orig).lower()
        if "employee_id" in message:
            raise EmployeeAlreadyLinked(
                "This employee already has a login account.") from exc
        raise UsernameTaken(
            f"Login username {username!r} is already in use.") from exc


def update_account(employee_id: int, *, role: str | None = None,
                   first_name: str | None = None, last_name: str | None = None,
                   employee_code: str | None = None,
                   disabled: bool | None = None) -> bool:
    if role is not None and role not in ROLES:
        raise AccountError(f"Unknown role: {role}")
    ensure_schema()
    with SessionLocal() as session:
        user = session.scalar(
            select(User).where(User.employee_id == employee_id)
        )
        if user is None:
            return False
        if role is not None:
            user.role = role
        if first_name is not None:
            user.first_name = first_name
        if last_name is not None:
            user.last_name = last_name
        if employee_code is not None:
            user.employee_code = employee_code
        if disabled is not None:
            user.disabled = int(disabled)
        if disabled:
            session.execute(
                delete(AuthSession).where(AuthSession.user_id == user.id)
            )
        session.commit()
    return True


def account_for_employee(employee_id: int) -> dict | None:
    ensure_schema()
    with SessionLocal() as session:
        row = session.execute(
            select(User.id, User.username, User.role, User.disabled)
            .where(User.employee_id == employee_id)
        ).mappings().first()
    return dict(row) if row else None


def change_password(employee_id: int, password: str) -> bool:
    """Set a linked browser login password and sign out its current sessions."""
    ensure_schema()
    with SessionLocal() as session:
        user = session.scalar(
            select(User).where(User.employee_id == employee_id)
        )
        if user is None:
            return False
        user.password_hash = hash_password(password)
        session.execute(
            delete(AuthSession).where(AuthSession.user_id == user.id)
        )
        session.commit()
    return True


def delete_account(employee_id: int) -> None:
    ensure_schema()
    with SessionLocal() as session:
        user = session.scalar(
            select(User).where(User.employee_id == employee_id)
        )
        if user is None:
            return
        tracker_ids = select(Tracker.id).where(
            Tracker.employee_id == employee_id
        )
        session.execute(
            delete(Device).where(Device.tracker_id.in_(tracker_ids))
        )
        session.execute(
            delete(Tracker).where(Tracker.employee_id == employee_id)
        )
        session.execute(delete(User).where(User.id == user.id))
        session.commit()


def delete_account_by_id(user_id: int) -> None:
    ensure_schema()
    with SessionLocal() as session:
        session.execute(delete(User).where(User.id == user_id))
        session.commit()


def disable_employee_trackers(employee_id: int) -> None:
    ensure_schema()
    with SessionLocal() as session:
        session.execute(
            update(Tracker)
            .where(Tracker.employee_id == employee_id)
            .values(disabled=1)
        )
        session.execute(
            update(Device)
            .where(
                Device.tracker_id.in_(
                    select(Tracker.id).where(
                        Tracker.employee_id == employee_id
                    )
                )
            )
            .values(revoked=1)
        )
        session.commit()
