from typing import Iterator

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import settings


class Base(DeclarativeBase):
    pass


def make_engine(url: str) -> Engine:
    """Create an engine. For SQLite, enforce foreign keys on every connection."""
    is_sqlite = url.startswith("sqlite")
    engine = create_engine(
        url,
        connect_args={"check_same_thread": False} if is_sqlite else {},
    )
    if is_sqlite:

        @event.listens_for(engine, "connect")
        def _set_sqlite_pragmas(dbapi_connection, _connection_record):
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")  # SQLite ignores FKs by default
            cursor.execute("PRAGMA busy_timeout=5000")
            cursor.close()

    return engine


engine = make_engine(settings.database_url)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db() -> Iterator[Session]:
    """FastAPI dependency: one database session per request."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def seed_defaults(db: Session) -> None:
    """Create the single fund-settings row if it doesn't exist yet."""
    from app.models import FundSettings  # imported here to avoid a circular import

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
    from app import models  # noqa: F401  (registers the models on Base)

    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        seed_defaults(db)
