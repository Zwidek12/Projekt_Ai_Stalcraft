from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sqlalchemy import Engine, create_engine, text
from sqlalchemy.engine.url import make_url
from sqlalchemy.orm import Session, sessionmaker

from .models import Base


@dataclass(frozen=True)
class Database:
    engine: Engine
    session_factory: sessionmaker[Session]


def create_database(database_url: str) -> Database:
    database_url = prepare_sqlite_database_url(database_url)
    connect_args = _sqlite_connect_args(database_url=database_url)
    engine_kwargs: dict[str, Any] = dict(future=True)
    if connect_args:
        engine_kwargs["connect_args"] = connect_args

    engine = create_engine(database_url, **engine_kwargs)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    return Database(engine=engine, session_factory=session_factory)


def prepare_sqlite_database_url(database_url: str, *, project_root: Path | None = None) -> str:
    """
    Ensure file-based SQLite URLs point at an existing parent directory.

    Without this, fresh clones fail with sqlite3.OperationalError: unable to open database file
    when `data/` has not been created yet.
    """
    raw = database_url.strip()
    if not raw:
        return raw

    parsed = make_url(raw)
    driver = parsed.drivername.split("+", 1)[0]
    if driver != "sqlite":
        return raw

    database = (parsed.database or "").strip()
    if not database or database == ":memory:":
        return raw

    db_path = Path(database)
    if not db_path.is_absolute():
        base = project_root if project_root is not None else Path.cwd()
        db_path = (base / db_path).resolve()

    db_path.parent.mkdir(parents=True, exist_ok=True)
    return str(parsed.set(database=db_path.as_posix()))


def _sqlite_connect_args(*, database_url: str) -> dict[str, Any] | None:
    """
    SQLite defaults can hang indefinitely waiting for locks when multiple writers exist.

    We set an explicit busy timeout so CLI jobs fail fast instead of silently blocking.
    """
    normalized = database_url.strip().lower()
    if not normalized.startswith(("sqlite:", "sqlite+pysqlite:", "sqlite+pysqlcipher:")):
        return None

    # seconds (SQLite uses milliseconds internally)
    return {"timeout": 30.0, "check_same_thread": False}


def init_schema(db: Database) -> None:
    Base.metadata.create_all(db.engine)
    _ensure_lightweight_columns(db)


def db_ping(db: Database) -> None:
    with db.engine.connect() as conn:
        conn.execute(text("SELECT 1"))


def _ensure_lightweight_columns(db: Database) -> None:
    """
    Small SQLite-friendly migrations for additive columns while this project has no Alembic yet.
    """
    with db.engine.begin() as conn:
        dialect = db.engine.dialect.name
        if dialect != "sqlite":
            return
        rows = conn.execute(text("PRAGMA table_info(price_history)")).fetchall()
        columns = {str(row[1]) for row in rows}
        if "rarity" not in columns:
            conn.execute(text("ALTER TABLE price_history ADD COLUMN rarity VARCHAR(32) NOT NULL DEFAULT 'unknown'"))

