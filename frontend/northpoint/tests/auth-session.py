"""Run from the repository root: uv run python frontend/northpoint/tests/auth-session.py.
Only a TemporaryDirectory database is used. Existing users and sessions are untouched.
"""
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import time

from starlette.requests import Request

with tempfile.TemporaryDirectory() as temporary:
    os.environ['AUTH_DB_PATH'] = str(Path(temporary) / 'session-test.db')
    source = Path.cwd() / 'auth' / 'main.py'
    spec = importlib.util.spec_from_file_location('isolated_auth_test', source)
    auth = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(auth)
    def request(token=''):
        return Request({'type': 'http', 'headers': [(b'cookie', ('auth_session=' + token).encode())]})
    assert auth.current_user(request()).status_code == 401
    assert auth.current_user(request('invalid')).status_code == 401
    with auth.db() as database:
        database.execute('INSERT INTO users VALUES (1,?,?,?)', ('Session Tester', 'unused-test-hash', int(time.time())))
        database.execute('INSERT INTO sessions VALUES (?,?,?)', (auth.hash_token('test-only-token'), 1, int(time.time()) + 60))
        database.commit()
    response = auth.current_user(request('test-only-token'))
    assert response.status_code == 200
    assert json.loads(response.body) == {'username': 'Session Tester'}
    assert response.headers['cache-control'] == 'no-store'
    with auth.db() as database:
        database.execute('UPDATE sessions SET expires_at=0')
        database.commit()
    assert auth.current_user(request('test-only-token')).status_code == 401
    print('Session endpoint: anonymous, invalid, valid and expired session checks passed; isolated DB only.')
