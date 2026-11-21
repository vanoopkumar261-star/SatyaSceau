"""SQLite engine, session dependency and the one timestamp helper.  Owner: Pile 1 (Platform)."""

from datetime import datetime, timezone

from sqlalchemy import inspect
from sqlmodel import Session, SQLModel, create_engine

from app.config import DATA_DIR, settings

DATA_DIR.mkdir(parents=True, exist_ok=True)

engine = create_engine(
    settings.DATABASE_URL,
    connect_args={"check_same_thread": False} if settings.DATABASE_URL.startswith("sqlite") else {},
)


def utcnow() -> datetime:
    """Timezone-aware UTC 'now'. Use this for EVERY timestamp.

    SQLModel stores aware datetimes and always returns them as aware UTC, so every
    value read from the DB can be compared with utcnow() directly.
    """
    return datetime.now(timezone.utc)


def as_utc(dt: datetime | None) -> datetime | None:
    """Normalise an incoming datetime to aware UTC. Naive input (no offset) is treated as UTC."""
    if dt is None:
        return None
    return dt.replace(tzinfo=timezone.utc) if dt.utcoffset() is None else dt.astimezone(timezone.utc)


def init_db(bind=engine) -> None:
    from app import models  # noqa: F401  (registers the tables)

    SQLModel.metadata.create_all(bind)
    _add_missing_columns(bind)


def _add_missing_columns(bind) -> None:
    """Tiny additive migration: when a model gains a column, add it to existing local DBs.

    create_all() never alters existing tables, so without this every teammate would have to
    delete backend/data/satyasceau.db after pulling. Existing rows get NULL in the new column.
    """
    insp = inspect(bind)
    with bind.begin() as conn:
        for table in SQLModel.metadata.sorted_tables:
            if not insp.has_table(table.name):
                continue
            existing = {col["name"] for col in insp.get_columns(table.name)}
            for col in table.columns:
                if col.name not in existing:
                    col_type = col.type.compile(dialect=bind.dialect)
                    conn.exec_driver_sql(f'ALTER TABLE "{table.name}" ADD COLUMN "{col.name}" {col_type}')


def get_session():
    """FastAPI dependency: one Session per request."""
    with Session(engine) as session:
        yield session
