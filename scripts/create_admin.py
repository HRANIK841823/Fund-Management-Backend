"""Create the first admin account.

Interactive:   python -m scripts.create_admin
Non-interactive: python -m scripts.create_admin --name "Admin" --username admin \
                   --email admin@example.com --password "a-long-password"
"""
import argparse
import getpass
import sys

from sqlalchemy import or_, select

from app.database import SessionLocal, init_db
from app.models import Role, User
from app.schemas import MemberCreate
from app.security import hash_password


def main() -> int:
    parser = argparse.ArgumentParser(description="Create an admin account.")
    parser.add_argument("--name")
    parser.add_argument("--username")
    parser.add_argument("--email")
    parser.add_argument("--password")
    args = parser.parse_args()

    name = args.name or input("Full name: ")
    username = args.username or input("Username: ")
    email = args.email or input("Email: ")
    password = args.password
    if not password:
        password = getpass.getpass("Password (min 8 characters): ")
        if password != getpass.getpass("Repeat password: "):
            print("Passwords do not match.")
            return 1

    try:
        data = MemberCreate(name=name, username=username, email=email, password=password)
    except Exception as exc:  # pydantic validation error
        print(f"Invalid input:\n{exc}")
        return 1

    init_db()
    with SessionLocal() as db:
        taken = db.scalar(
            select(User).where(or_(User.username == data.username, User.email == data.email))
        )
        if taken:
            print("A user with that username or email already exists.")
            return 1
        db.add(
            User(
                name=data.name,
                username=data.username,
                email=data.email,
                password_hash=hash_password(data.password),
                role=Role.ADMIN,
            )
        )
        db.commit()
    print(f"Admin '{data.username}' created. You can now log in.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
