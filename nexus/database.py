"""SQLite connection and schema initialization."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from nexus.config import settings

_connection: sqlite3.Connection | None = None


def get_connection(db_path: Path | None = None) -> sqlite3.Connection:
    path = db_path or settings.database_path
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(conn: sqlite3.Connection | None = None) -> sqlite3.Connection:
    db = conn or get_connection()
    schema_path = Path(__file__).parent / "schema.sql"
    db.executescript(schema_path.read_text(encoding="utf-8"))
    db.commit()
    return db


def get_db() -> sqlite3.Connection:
    """Return the shared application database connection."""
    global _connection
    if _connection is None:
        _connection = init_db()
    return _connection


def reset_db_connection() -> None:
    """Close and clear the shared connection (used by tests and restart simulation)."""
    global _connection
    if _connection is not None:
        _connection.close()
        _connection = None
