"""Engine/session factory and schema initialisation."""

from __future__ import annotations

import logging
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from sqlalchemy import Engine, create_engine, event, text
from sqlalchemy.orm import Session, sessionmaker

from .models import Base

log = logging.getLogger("gridstorm_api.db")


def is_postgres(engine: Engine) -> bool:
    return engine.dialect.name == "postgresql"


def normalise_url(url: str) -> str:
    """Use psycopg 3 for plain ``postgres://`` / ``postgresql://`` URLs (Supabase/Render style)."""
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://") :]
    if url.startswith("postgresql://"):
        url = "postgresql+psycopg://" + url[len("postgresql://") :]
    return url


def make_engine(url: str) -> Engine:
    url = normalise_url(url)
    kwargs: dict[str, Any] = {"future": True}
    if url.startswith("sqlite"):
        if url.startswith("sqlite:///") and ":memory:" not in url:
            Path(url[len("sqlite:///") :]).parent.mkdir(parents=True, exist_ok=True)
        kwargs["connect_args"] = {"check_same_thread": False, "timeout": 30}
        engine = create_engine(url, **kwargs)

        @event.listens_for(engine, "connect")
        def _sqlite_pragmas(dbapi_conn: Any, _: Any) -> None:
            cur = dbapi_conn.cursor()
            cur.execute("PRAGMA foreign_keys=ON")
            cur.execute("PRAGMA journal_mode=WAL")
            cur.execute("PRAGMA busy_timeout=30000")
            cur.close()

        return engine
    # prepare_threshold=None: no server-side prepared statements, so the Supabase transaction
    # pooler (pgbouncer, port 6543) works as well as a direct connection.
    kwargs["connect_args"] = {"prepare_threshold": None}
    kwargs["pool_pre_ping"] = True
    kwargs["pool_size"] = 5
    kwargs["max_overflow"] = 5
    return create_engine(url, **kwargs)


class Database:
    def __init__(self, url: str) -> None:
        self.engine = make_engine(url)
        self.sessionmaker = sessionmaker(self.engine, expire_on_commit=False, future=True)

    @property
    def is_postgres(self) -> bool:
        return is_postgres(self.engine)

    def init_schema(self, *, migrations_dir: Path, auto_migrate: bool, supabase_stub: bool) -> None:
        """SQLite: create tables from ORM metadata. Postgres: optionally apply SQL migrations."""
        if self.is_postgres:
            if auto_migrate:
                # Imported lazily so `python -m gridstorm_api.db.migrate` does not pre-import it.
                from .migrate import apply_migrations

                applied = apply_migrations(self.engine, migrations_dir, supabase_stub=supabase_stub)
                log.info("applied %d migration(s): %s", len(applied), applied)
            return
        Base.metadata.create_all(self.engine)

    @contextmanager
    def session(self) -> Iterator[Session]:
        with self.sessionmaker() as s:
            yield s

    def ping(self) -> None:
        with self.engine.connect() as conn:
            conn.execute(text("select 1"))

    def dispose(self) -> None:
        self.engine.dispose()
