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
    routes = [route for route in auth.auth_app.routes
              if getattr(route, 'path', None) == '/me' and 'GET' in route.methods]
    assert len(routes) == 1, 'GET /me must have exactly one registered handler'
    endpoint = routes[0].endpoint
    assert endpoint is auth.me
    assert endpoint(request()).status_code == 401
    assert endpoint(request('invalid')).status_code == 401
    with auth.db() as database:
        database.execute(
            'INSERT INTO users (id,username,password_hash,created_at,first_name,last_name) VALUES (1,?,?,?,?,?)',
            ('session-tester', 'unused-test-hash', int(time.time()), 'Session', 'Tester'))
        database.execute(
            'INSERT INTO sessions (token_hash,user_id,expires_at) VALUES (?,?,?)',
            (auth.hash_token('test-only-token'), 1, int(time.time()) + 3600))
        database.commit()
    response = endpoint(request('test-only-token'))
    assert response.status_code == 200
    assert json.loads(response.body) == {
        'id': 1, 'username': 'session-tester', 'first_name': 'Session',
        'last_name': 'Tester', 'full_name': 'Session Tester'}
    assert response.headers['cache-control'] == 'no-store'
    # Existing accounts without profile names still expose their username.
    with auth.db() as database:
        database.execute('UPDATE users SET first_name=NULL,last_name=NULL WHERE id=1')
        database.commit()
    profile = json.loads(endpoint(request('test-only-token')).body)
    assert profile['full_name'] == profile['username'] == 'session-tester'
    assert profile['first_name'] is None and profile['last_name'] is None
    with auth.db() as database:
        database.execute('UPDATE sessions SET expires_at=0')
        database.commit()
    assert endpoint(request('test-only-token')).status_code == 401
    with auth.db() as database:
        database.execute('UPDATE sessions SET expires_at=?', (int(time.time()) + 3600,))
        database.commit()
    assert endpoint(request('test-only-token')).status_code == 200
    logout = auth.logout(request('test-only-token'))
    assert logout.status_code == 303
    assert logout.headers['location'] == '/auth/login'
    assert 'Max-Age=0' in logout.headers['set-cookie']
    assert endpoint(request('test-only-token')).status_code == 401
    with auth.db() as database:
        assert database.execute('SELECT COUNT(*) FROM sessions').fetchone()[0] == 0
    print('Session endpoint: unique route, anonymous, invalid, valid, unnamed account, no-store, expired and logout checks passed; isolated DB only.')
