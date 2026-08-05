"""
Interactive first-run account creation. Run this once on a fresh install
(after `python -m app.seed --config-only`) to create a real login instead of
ever using the demo1234 accounts on a real install.

Usage:
    venv\\Scripts\\python -m app.create_user

Safe to re-run: if the username already exists, it updates that user's
password/name/role rather than creating a duplicate -- also how you reset a
forgotten password later.
"""
import getpass

from app.db import SessionLocal, engine
from app.db_migrate import run_migrations
from app.models.models import AuditEvent, User
from app.services.auth_service import hash_password

ROLES = ["SCIENTIST", "SCIENTIFIC_ASSISTANT", "ADMINISTRATOR"]


def prompt_role() -> str:
    print("Roles: 1) Scientist  2) Scientific Assistant  3) Administrator")
    while True:
        choice = input("Select role [1/2/3]: ").strip()
        if choice in ("1", "2", "3"):
            return ROLES[int(choice) - 1]
        print("Please enter 1, 2, or 3.")


def main():
    # B1 (Review #2 remediation): run_migrations(), not create_all() -- see
    # seed.py's run() for the full explanation. Both of this app's two
    # schema-creation call sites outside main.py's own startup must go
    # through the same Alembic-driven path so a fresh install (which runs
    # this script right after `seed.py --config-only`, per
    # first_time_setup.bat) never has a schema with no alembic_version row.
    run_migrations(engine)
    db = SessionLocal()
    try:
        print("=== CableLIMS -- create or update a login ===")
        username = input("Username (e.g. jsmith): ").strip()
        if not username:
            print("Username cannot be empty. Aborted.")
            return
        full_name = input("Full name (e.g. Dr. John Smith): ").strip() or username
        role = prompt_role()

        while True:
            password = getpass.getpass("Password (input hidden): ")
            confirm = getpass.getpass("Confirm password: ")
            if password != confirm:
                print("Passwords didn't match, try again.")
                continue
            if len(password) < 8:
                print("Use at least 8 characters.")
                continue
            break

        existing = db.query(User).filter(User.username == username).first()
        if existing:
            existing.password_hash = hash_password(password)
            existing.full_name = full_name
            existing.role = role
            action = "USER_UPDATED"
            print(f"Updated existing account '{username}'.")
        else:
            db.add(User(username=username, full_name=full_name, role=role,
                         password_hash=hash_password(password)))
            action = "USER_CREATED"
            print(f"Created account '{username}' ({role}).")

        db.add(AuditEvent(actor_name="setup", action=action, entity_type="user",
                           entity_id=username, details={"role": role}))
        db.commit()
        print("Done. You can log in with this account now.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
