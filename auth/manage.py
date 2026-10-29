import argparse, getpass, secrets, time
from contextlib import closing

from auth.main import db, hash_password, hash_token


def create_user(a):
    first = input("First name: ").strip()
    last = input("Last name: ").strip()
    if not first or not last:
        raise SystemExit("First and last name are required.")
    pw = getpass.getpass("Password: ")
    if len(pw) < 10 or pw != getpass.getpass("Again: "):
        raise SystemExit("Passwords differ or are shorter than 10 characters.")
    with closing(db()) as c, c:
        c.execute(
            "INSERT INTO users(username,password_hash,first_name,last_name,created_at) "
            "VALUES(?,?,?,?,?) ON CONFLICT(username) DO UPDATE SET "
            "password_hash=excluded.password_hash, first_name=excluded.first_name, "
            "last_name=excluded.last_name",
            (a.name, hash_password(pw), first, last, int(time.time())))
        c.execute("DELETE FROM sessions WHERE user_id=(SELECT id FROM users WHERE username=?)",
                  (a.name,))
    print(f"User '{a.name}' saved as {first} {last}.")

def set_name(a):
    """Change the name only, keeping the password and sessions."""
    first = input("First name: ").strip()
    last = input("Last name: ").strip()
    if not first or not last:
        raise SystemExit("First and last name are required.")
    with closing(db()) as c, c:
        cur = c.execute("UPDATE users SET first_name=?, last_name=? WHERE username=?",
                        (first, last, a.name))
    print("Updated." if cur.rowcount else f"No user '{a.name}'.")

def add_device(a):
    token = secrets.token_urlsafe(32)
    with closing(db()) as c, c:
        c.execute("INSERT INTO devices(name,token_hash,created_at) VALUES(?,?,?)",
                  (a.name, hash_token(token), int(time.time())))
    print(f"Token for '{a.name}' (shown once, copy it now):\n{token}")


def revoke_device(a):
    with closing(db()) as c, c:
        c.execute("UPDATE devices SET revoked=1 WHERE name=?", (a.name,))
    print(f"Device '{a.name}' revoked.")


def list_all(a):
    with closing(db()) as c:
        for r in c.execute("SELECT username, first_name, last_name FROM users"):
            name = f"{r['first_name'] or ''} {r['last_name'] or ''}".strip()
            print("User:", r["username"], f"({name})" if name else "(no name set)")
        for r in c.execute("SELECT username, disabled FROM trackers"):
            print("Tracker:", r["username"], "(disabled)" if r["disabled"] else "(active)")
        for r in c.execute("SELECT name, revoked FROM devices"):
            print("Device:", r["name"], "(revoked)" if r["revoked"] else "(active)")

def create_tracker(a):
    pw = getpass.getpass("Password: ")
    if len(pw) < 8 or pw != getpass.getpass("Again: "):
        raise SystemExit("Passwords differ or are shorter than 8 characters.")
    with closing(db()) as c, c:
        c.execute(
            "INSERT INTO trackers(username,password_hash,created_at) VALUES(?,?,?) "
            "ON CONFLICT(username) DO UPDATE SET password_hash=excluded.password_hash, disabled=0",
            (a.name, hash_password(pw), int(time.time())))
        # a password change logs the phone out
        c.execute("UPDATE devices SET revoked=1 WHERE tracker_id="
                  "(SELECT id FROM trackers WHERE username=?)", (a.name,))
    print(f"Tracker '{a.name}' saved.")


def disable_tracker(a):
    with closing(db()) as c, c:
        c.execute("UPDATE trackers SET disabled=1 WHERE username=?", (a.name,))
        c.execute("UPDATE devices SET revoked=1 WHERE tracker_id="
                  "(SELECT id FROM trackers WHERE username=?)", (a.name,))
    print(f"Tracker '{a.name}' disabled and its phones logged out.")


p = argparse.ArgumentParser()
s = p.add_subparsers(required=True)
for cmd, fn in [("create-user", create_user), ("add-device", add_device),
                ("revoke-device", revoke_device),
                ("create-tracker", create_tracker),
                ("set-name", set_name),
                ("disable-tracker", disable_tracker)]:
    sp = s.add_parser(cmd); sp.add_argument("name"); sp.set_defaults(fn=fn)
s.add_parser("list").set_defaults(fn=list_all)
a = p.parse_args(); a.fn(a)
