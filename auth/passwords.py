"""HR-only password changes for linked browser login accounts.

Tracker (mobile app) passwords remain part of the mobile-access endpoints.
Both account types are writable by HR only.
"""
from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, ConfigDict, Field

from auth import accounts
from auth.mobile_access import browser_user

router = APIRouter()


class LoginPasswordChange(BaseModel):
    model_config = ConfigDict(extra='forbid')
    password: str = Field(min_length=10, max_length=128)


@router.get('/employees/{employee_id}/login-account')
def login_account(employee_id: int, response: Response,
                  user=Depends(browser_user)):
    account = accounts.account_for_employee(employee_id)
    if account is None:
        raise HTTPException(
            404, 'This employee does not have a website login account.')
    response.headers['Cache-Control'] = 'no-store'
    return {'username': account['username'],
            'disabled': bool(account['disabled'])}


@router.patch('/employees/{employee_id}/password')
def change_login_password(employee_id: int, body: LoginPasswordChange,
                          user=Depends(browser_user)):
    if not accounts.change_password(employee_id, body.password):
        raise HTTPException(
            404, 'This employee does not have a website login account.')
    return {'message': 'Website login password updated. Existing browser '
                       'sessions for this employee were signed out.'}
