"""Persistence layer (SQLAlchemy 2.x; Postgres via psycopg 3, SQLite fallback)."""

from .session import Database, is_postgres

__all__ = ["Database", "is_postgres"]
