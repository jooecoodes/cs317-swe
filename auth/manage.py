import argparse, getpass, secrets, time

from sqlalchemy import delete, select, update

from auth.db import AuthSession, Device, SessionLocal, Tracker, User
from auth.main import hash_password, hash_token, ROLES, DEFAULT_ROLE


def valid_role(role):
    role = (role or "").strip().lower()
    if role not in ROLES:
        raise SystemExit(f"Role must be one of: {', '.join(ROLES)}.")
    return role


def prompt_role():
    print("Roles:", ", ".join(ROLES))
    role = input(f"Role [{DEFAULT_ROLE}]: ").strip() or DEFAULT_ROLE
    return valid_role(role)


def create_user(a):
    first = input("First name: ").strip()
    last = input("Last name: ").strip()
    if not first or not last:
        raise SystemExit("First and last name are required.")
    role = valid_role(a.role) if a.role else prompt_role()
    pw = getpass.getpass("Password: ")
    if len(pw) < 10 or pw != getpass.getpass("Again: "):
        raise SystemExit("Passwords differ or are shorter than 10 characters.")
    with SessionLocal() as session:
        user = session.scalar(select(User).where(User.username == a.name))
        if user is None:
            user = User(username=a.name, created_at=int(time.time()))
            session.add(user)
        user.password_hash = hash_password(pw)
        user.first_name = first
        user.last_name = last
        user.role = role
        session.flush()
        session.execute(
            delete(AuthSession).where(AuthSession.user_id == user.id)
        )
        session.commit()
    print(f"User '{a.name}' saved as {first} {last} ({role}).")

def set_role(a):
    role = valid_role(a.role)
    with SessionLocal() as session:
        result = session.execute(
            update(User).where(User.username == a.name).values(role=role)
        )
        session.commit()
    print(f"Role updated to {role}." if result.rowcount else f"No user '{a.name}'.")


def set_name(a):
    """Change the name only, keeping the password and sessions."""
    first = input("First name: ").strip()
    last = input("Last name: ").strip()
    if not first or not last:
        raise SystemExit("First and last name are required.")
    with SessionLocal() as session:
        result = session.execute(
            update(User)
            .where(User.username == a.name)
            .values(first_name=first, last_name=last)
        )
        session.commit()
    print("Updated." if result.rowcount else f"No user '{a.name}'.")

def add_device(a):
    token = secrets.token_urlsafe(32)
    with SessionLocal() as session:
        session.add(Device(
            name=a.name,
            token_hash=hash_token(token),
            created_at=int(time.time()),
        ))
        session.commit()
    print(f"Token for '{a.name}' (shown once, copy it now):\n{token}")


def revoke_device(a):
    with SessionLocal() as session:
        session.execute(
            update(Device).where(Device.name == a.name).values(revoked=1)
        )
        session.commit()
    print(f"Device '{a.name}' revoked.")


def list_all(a):
    with SessionLocal() as session:
        for r in session.scalars(select(User).order_by(User.id)):
            name = f"{r.first_name or ''} {r.last_name or ''}".strip()
            print("User:", r.username, f"({name})" if name else "(no name set)",
                  f"[{r.role}]")
        for r in session.scalars(select(Tracker).order_by(Tracker.id)):
            print("Tracker:", r.username, "(disabled)" if r.disabled else "(active)")
        for r in session.scalars(select(Device).order_by(Device.id)):
            print("Device:", r.name, "(revoked)" if r.revoked else "(active)")

def create_tracker(a):
    pw = getpass.getpass("Password: ")
    if len(pw) < 8 or pw != getpass.getpass("Again: "):
        raise SystemExit("Passwords differ or are shorter than 8 characters.")
    with SessionLocal() as session:
        tracker = session.scalar(
            select(Tracker).where(Tracker.username == a.name)
        )
        if tracker is None:
            tracker = Tracker(username=a.name, created_at=int(time.time()))
            session.add(tracker)
        tracker.password_hash = hash_password(pw)
        tracker.disabled = 0
        session.flush()
        # a password change logs the phone out
        session.execute(
            update(Device)
            .where(Device.tracker_id == tracker.id)
            .values(revoked=1)
        )
        session.commit()
    print(f"Tracker '{a.name}' saved.")


def disable_tracker(a):
    with SessionLocal() as session:
        tracker = session.scalar(
            select(Tracker).where(Tracker.username == a.name)
        )
        if tracker is not None:
            tracker.disabled = 1
            session.execute(
                update(Device)
                .where(Device.tracker_id == tracker.id)
                .values(revoked=1)
            )
            session.commit()
    print(f"Tracker '{a.name}' disabled and its phones logged out.")


p = argparse.ArgumentParser()
s = p.add_subparsers(required=True)
for cmd, fn in [("create-user", create_user), ("add-device", add_device),
                ("revoke-device", revoke_device),
                ("create-tracker", create_tracker),
                ("set-name", set_name),
                ("set-role", set_role),
                ("disable-tracker", disable_tracker)]:
    sp = s.add_parser(cmd); sp.add_argument("name")
    if fn is create_user:
        sp.add_argument("--role", choices=ROLES,
                        help="account role; prompts when omitted")
    elif fn is set_role:
        sp.add_argument("--role", choices=ROLES, required=True)
    sp.set_defaults(fn=fn)
s.add_parser("list").set_defaults(fn=list_all)
a = p.parse_args(); a.fn(a)
