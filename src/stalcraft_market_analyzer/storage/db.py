from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import Engine, create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from .models import Base


@dataclass(frozen=True)
class Database:
    engine: Engine
    session_factory: sessionmaker[Session]


def create_database(database_url: str) -> Database:
    engine = create_engine(database_url, future=True)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    return Database(engine=engine, session_factory=session_factory)


def init_schema(db: Database) -> None:
    Base.metadata.create_all(db.engine)


def db_ping(db: Database) -> None:
    with db.engine.connect() as conn:
        conn.execute(text("SELECT 1"))

