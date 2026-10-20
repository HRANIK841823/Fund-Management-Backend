import os
from typing import Iterator

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import settings

load_dotenv()


class Base(DeclarativeBase):
    pass


# Supabase PostgreSQL configuration
USER = os.getenv("user")
PASSWORD = os.getenv("password")
HOST = os.getenv("host")
PORT = os.getenv("port")
DBNAME = os.getenv("dbname")

if not all([USER, PASSWORD, HOST, PORT, DBNAME]):
    raise ValueError(
        "Supabase database configuration is incomplete. "
        "Check user, password, host, port, and dbname in .env"
    )

DATABASE_URL = (
    f"postgresql+psycopg2://{USER}:{PASSWORD}@{HOST}:{PORT}/{DBNAME}?sslmode=require"
)


def make_engine(url: str) -> Engine:
    """Create a PostgreSQL engine."""
    return create_engine(
        url,
        pool_pre_ping=True,
    )


engine = make_engine(DATABASE_URL)

SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    expire_on_commit=False,
)


def get_db() -> Iterator[Session]:
    """FastAPI dependency: one database session per request."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def seed_defaults(db: Session) -> None:
    """Create the single fund-settings row if it doesn't exist yet."""
    from app.models import FundSettings

    if db.get(FundSettings, 1) is None:
        db.add(
            FundSettings(
                id=1,
                monthly_contribution_amount=settings.default_monthly_contribution,
            )
        )
        db.commit()


def init_db() -> None:
    """Create all tables (if missing) and seed default settings."""
    from app import models  # noqa: F401

    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        seed_defaults(db)


# Test database connection
try:
    with engine.connect():
        print("Supabase PostgreSQL connection successful!")
except Exception as e:
    print(f"Failed to connect to Supabase PostgreSQL: {e}")
    raise