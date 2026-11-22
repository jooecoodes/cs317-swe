"""Browser-managed tracker access and server-resolved employee identity.

SQLite files remain separate. The auth database owns the unique employee link;
only a read-only connection is used to look up HR records.
"""
import os
import sqlite3
import time
from contextlib import closing
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import or_, select, text, update
from sqlalchemy.exc import IntegrityError

from auth.db import AuthSession, Device, SessionLocal, Tracker, User

router = APIRouter()


def auth():
    from auth import main
    return main


def employee(employee_id: int, *, active=False, supervisor=False):
    path = Path(os.getenv('APP1_DB_PATH', Path(__file__).resolve().parents[1] / 'data/app1/app.db')).resolve()
    try:
        with closing(sqlite3.connect(path.as_uri() + '?mode=ro', uri=True)) as c:
            c.row_factory = sqlite3.Row
            row = c.execute('SELECT id, employee_code, first_name, last_name, status, employee_type FROM employees WHERE id=?', (employee_id,)).fetchone()
    except sqlite3.Error:
        raise HTTPException(503, 'Employee records are temporarily unavailable. Please try again.')
    if not row:
        raise HTTPException(404, 'This employee no longer exists. Refresh the employee list.')
    if active and row['status'] != 'active':
        raise HTTPException(403, 'This employee is inactive. Ask HR to reactivate the employee profile first.')
    if supervisor and row['employee_type'] != 'supervisor':
        raise HTTPException(403, 'Only employees with the Supervisor type can have a mobile tracker account.')
    return {'employee_id': row['id'], 'employee_code': row['employee_code'],
            'full_name': f"{row['first_name']} {row['last_name']}",
            'status': row['status'], 'employee_type': row['employee_type']}


def browser_user(request: Request):
    a = auth()
    with SessionLocal() as session:
        row = session.execute(
            select(User.id, User.username, User.role, User.employee_id)
            .join(AuthSession, AuthSession.user_id == User.id)
            .where(
                AuthSession.token_hash == a.hash_token(
                    request.cookies.get(a.COOKIE, '')
                ),
                AuthSession.expires_at > int(time.time()),
                User.disabled == 0,
            )
        ).first()
    if not row:
        raise HTTPException(401, 'Please sign in to the HR website again.')
    if row.role != 'hr':
        raise HTTPException(403, 'Only HR can manage mobile tracker access.')
    # Custom header + JSON prevents cross-origin form submissions; no CORS grant.
    if request.method != 'GET' and request.headers.get('x-requested-with') != 'Northpoint':
        raise HTTPException(403, 'Please use Mobile App Access on the HR website.')
    return dict(row._mapping)


def tracker_identity(request: Request):
    a = auth()
    bearer = request.headers.get('authorization', '')
    if not bearer.lower().startswith('bearer '):
        raise HTTPException(401, 'Please sign in to the mobile app again.')
    now = int(time.time())
    with SessionLocal() as session:
        row = session.execute(
            select(
                Device.id,
                Tracker.id.label('tracker_id'),
                Tracker.username,
                Tracker.employee_id,
                Tracker.employee_code,
            )
            .join(Tracker, Tracker.id == Device.tracker_id)
            .where(
                Device.token_hash == a.hash_token(bearer[7:].strip()),
                Device.revoked == 0,
                Tracker.disabled == 0,
                or_(Device.expires_at.is_(None), Device.expires_at > now),
            )
        ).first()
        if not row:
            raise HTTPException(401, 'Your mobile session has expired or was disabled. Please sign in again.')
        if not row.employee_id:
            raise HTTPException(403, 'Your account is not linked to an employee. Ask HR to open Mobile App Access.')
        info = employee(row.employee_id, active=True, supervisor=True)
        if info['employee_code'] != row.employee_code:
            raise HTTPException(403, 'The employee record has changed. Ask HR to check your mobile access.')
        session.execute(
            update(Device)
            .where(Device.id == row.id)
            .values(last_used=now, expires_at=now + a.DEVICE_TTL)
        )
        session.commit()
    return {**info, 'tracker_id': row.tracker_id, 'username': row.username}


class AccountCreate(BaseModel):
    model_config = ConfigDict(extra='forbid')
    username: str = Field(min_length=3, max_length=50, pattern=r'^[A-Za-z0-9][A-Za-z0-9._-]+$')
    password: str = Field(min_length=10, max_length=128)


class AccountChange(BaseModel):
    model_config = ConfigDict(extra='forbid')
    password: str | None = Field(default=None, min_length=10, max_length=128)
    disabled: bool | None = None


@router.get('/device-me')
def device_me(response: Response, info=Depends(tracker_identity)):
    response.headers['Cache-Control'] = 'no-store'
    return info


@router.get('/employees/{employee_id}/mobile-access')
def access_status(employee_id: int, response: Response, user=Depends(browser_user)):
    info = employee(employee_id)
    response.headers['Cache-Control'] = 'no-store'
    with SessionLocal() as session:
        row = session.execute(
            select(Tracker.username, Tracker.disabled)
            .where(Tracker.employee_id == employee_id)
        ).mappings().first()
    return {**info, 'eligible': info['employee_type'] == 'supervisor',
            'account': dict(row) if row else None}


@router.post('/employees/{employee_id}/mobile-access', status_code=201)
def create_access(employee_id: int, body: AccountCreate, response: Response, user=Depends(browser_user)):
    info = employee(employee_id, active=True, supervisor=True)
    a = auth()
    try:
        with SessionLocal() as session:
            session.add(Tracker(
                username=body.username,
                password_hash=a.hash_password(body.password),
                created_at=int(time.time()),
                employee_id=employee_id,
                employee_code=info['employee_code'],
            ))
            session.commit()
    except IntegrityError:
        raise HTTPException(409, 'This username or employee already has a mobile account. Refresh Mobile App Access or choose another username.')
    response.headers['Cache-Control'] = 'no-store'
    return {**info, 'account': {'username': body.username, 'disabled': False},
            'message': f"Mobile account created for {info['full_name']}. The employee can now sign in."}


@router.post('/employees/{employee_id}/mobile-access/link')
def link_existing(employee_id: int, body: AccountCreate, response: Response, user=Depends(browser_user)):
    """HR may explicitly claim an unlinked legacy tracker and reset its password."""
    info = employee(employee_id, active=True, supervisor=True)
    a = auth()
    try:
        with SessionLocal() as session:
            session.execute(text('BEGIN IMMEDIATE'))
            row = session.execute(
                select(Tracker.id, Tracker.employee_id)
                .where(Tracker.username == body.username)
            ).first()
            if not row:
                raise HTTPException(404, 'That mobile username does not exist. Use Create Mobile Account instead.')
            if row.employee_id is not None:
                raise HTTPException(409, 'That account is already linked. Open the linked employee profile instead.')
            session.execute(
                update(Tracker)
                .where(Tracker.id == row.id)
                .values(
                    employee_id=employee_id,
                    employee_code=info['employee_code'],
                    password_hash=a.hash_password(body.password),
                    disabled=0,
                )
            )
            session.execute(
                update(Device)
                .where(Device.tracker_id == row.id)
                .values(revoked=1)
            )
            session.commit()
    except IntegrityError:
        raise HTTPException(409, 'This employee already has a mobile account. Refresh this section.')
    response.headers['Cache-Control'] = 'no-store'
    return {'message': 'Existing account linked and password reset. Ask the employee to sign in again.'}


@router.patch('/employees/{employee_id}/mobile-access')
def change_access(employee_id: int, body: AccountChange, user=Depends(browser_user)):
    employee(employee_id, active=body.disabled is False, supervisor=True)
    if body.password is None and body.disabled is None:
        raise HTTPException(422, 'Enter a new password or choose an access status.')
    a = auth()
    with SessionLocal() as session:
        row = session.execute(
            select(Tracker.id).where(Tracker.employee_id == employee_id)
        ).first()
        if not row:
            raise HTTPException(404, 'Create a mobile account for this employee first.')
        if body.password is not None:
            session.execute(
                update(Tracker)
                .where(Tracker.id == row.id)
                .values(password_hash=a.hash_password(body.password))
            )
        if body.disabled is not None:
            session.execute(
                update(Tracker)
                .where(Tracker.id == row.id)
                .values(disabled=int(body.disabled))
            )
        if body.password is not None or body.disabled:
            session.execute(
                update(Device)
                .where(Device.tracker_id == row.id)
                .values(revoked=1)
            )
        session.commit()
    return {'message': 'Mobile access updated. Password changes or disabling access sign out existing phones.'}
