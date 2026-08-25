"""Postgres connection pool and query helpers."""

from contextlib import contextmanager
from pathlib import Path
from typing import Generator

from psycopg import Cursor
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from app.config import DATABASE_URL

SCHEMA_PATH = Path(__file__).resolve().parent / "schema.sql"

pool = ConnectionPool(
    DATABASE_URL,
    min_size=1,
    max_size=10,
    open=False,
    kwargs={"row_factory": dict_row},
)


def apply_schema() -> None:
    """Create tables if missing. Safe to run repeatedly."""
    with pool.connection() as conn:
        conn.execute(SCHEMA_PATH.read_text(encoding="utf-8"))


def fetch_one(sql: str, params: tuple = ()) -> dict | None:
    """Return the first row, or None."""
    with pool.connection() as conn, conn.cursor() as cur:
        cur.execute(sql, params)
        return cur.fetchone()


def fetch_all(sql: str, params: tuple = ()) -> list[dict]:
    """Return every matching row."""
    with pool.connection() as conn, conn.cursor() as cur:
        cur.execute(sql, params)
        return cur.fetchall()


def execute(sql: str, params: tuple = ()) -> int:
    """Run a statement, return rows affected."""
    with pool.connection() as conn, conn.cursor() as cur:
        cur.execute(sql, params)
        return cur.rowcount


@contextmanager
def transaction() -> Generator[Cursor, None, None]:
    """Run several statements atomically. All commit, or none do."""
    with pool.connection() as conn, conn.cursor() as cur:
        yield cur
