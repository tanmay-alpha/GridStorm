"""Apply ``database/migrations/*.sql`` to a Postgres database (Supabase or plain Postgres).

Usage::

    DATABASE_URL=postgresql://... uv run python -m gridstorm_api.db.migrate [--supabase-stub]

Each file runs in its own transaction and is recorded in ``public.schema_migrations``; files are
applied in lexical order and never re-applied. ``--supabase-stub`` first creates a minimal
stand-in for Supabase's ``auth`` schema and roles (``database/dev/supabase_auth_stub.sql``) so
the same migrations run on a plain ``postgres:16`` (docker-compose, tests). Never use the stub
against a real Supabase project.
"""

from __future__ import annotations

import argparse
import hashlib
import logging
import os
from pathlib import Path

from sqlalchemy import Engine, text

log = logging.getLogger("gridstorm_api.db.migrate")

_LOCK_KEY = 0x6772696473746F  # arbitrary constant for pg_advisory_xact_lock ("gridsto")

_BOOTSTRAP = """
create table if not exists public.schema_migrations (
    version text primary key,
    sha256 text not null,
    applied_at timestamptz not null default now()
);
alter table public.schema_migrations enable row level security;
"""


def stub_path(migrations_dir: Path) -> Path:
    return migrations_dir.parent / "dev" / "supabase_auth_stub.sql"


def _run_script(conn, sql: str) -> None:  # type: ignore[no-untyped-def]
    # Use the DBAPI connection directly: psycopg 3 accepts multi-statement scripts (dollar-quoted
    # function bodies included) when no parameters are passed.
    dbapi = conn.connection.driver_connection
    dbapi.execute(sql)


def apply_migrations(
    engine: Engine, migrations_dir: Path, *, supabase_stub: bool = False
) -> list[str]:
    if engine.dialect.name != "postgresql":
        raise RuntimeError("SQL migrations target Postgres; SQLite uses ORM create_all")
    files = sorted(migrations_dir.glob("*.sql"))
    if not files:
        raise FileNotFoundError(f"no migrations found in {migrations_dir}")
    applied: list[str] = []
    with engine.begin() as conn:
        conn.execute(text("select pg_advisory_xact_lock(:k)"), {"k": _LOCK_KEY})
        if supabase_stub:
            _run_script(conn, stub_path(migrations_dir).read_text(encoding="utf-8"))
        _run_script(conn, _BOOTSTRAP)
        done = {
            row[0]: row[1]
            for row in conn.execute(text("select version, sha256 from public.schema_migrations"))
        }
        for f in files:
            body = f.read_text(encoding="utf-8")
            digest = hashlib.sha256(body.encode("utf-8")).hexdigest()
            if f.name in done:
                if done[f.name] != digest:
                    log.warning("migration %s changed after being applied (sha mismatch)", f.name)
                continue
            log.info("applying migration %s", f.name)
            _run_script(conn, body)
            conn.execute(
                text("insert into public.schema_migrations (version, sha256) values (:v, :s)"),
                {"v": f.name, "s": digest},
            )
            applied.append(f.name)
    return applied


def main(argv: list[str] | None = None) -> int:
    from ..config import Settings
    from .session import make_engine

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--supabase-stub", action="store_true")
    parser.add_argument("--migrations-dir", type=Path, default=None)
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO)
    settings = Settings.from_env()
    url = os.environ.get("DATABASE_URL")
    if not url:
        parser.error("DATABASE_URL must point at a Postgres database")
    engine = make_engine(url)
    applied = apply_migrations(
        engine,
        args.migrations_dir or settings.migrations_dir,
        supabase_stub=args.supabase_stub or settings.db_supabase_stub,
    )
    print(f"applied {len(applied)} migration(s): {', '.join(applied) or '-'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
