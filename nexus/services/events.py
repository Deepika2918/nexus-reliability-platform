"""Append-only event recording and queries."""

from __future__ import annotations

import json
import sqlite3
from typing import Any

from nexus.clock import clock


def record_event(
    conn: sqlite3.Connection,
    *,
    event_type: str,
    subject_type: str,
    subject_id: str,
    action: str,
    reason: str,
    details: dict[str, Any] | None = None,
) -> int:
    cursor = conn.execute(
        """
        INSERT INTO events (timestamp, event_type, subject_type, subject_id, action, reason, details)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            clock.iso_now(),
            event_type,
            subject_type,
            subject_id,
            action,
            reason,
            json.dumps(details) if details is not None else None,
        ),
    )
    return cursor.lastrowid or 0


def list_event_actions(conn: sqlite3.Connection, subject_id: str) -> list[str]:
    rows = conn.execute(
        "SELECT action FROM events WHERE subject_id = ? ORDER BY id ASC",
        (subject_id,),
    ).fetchall()
    return [row["action"] for row in rows]


def _extract_ids(
    subject_type: str,
    subject_id: str,
    details: dict | None,
) -> tuple[str | None, str | None]:
    work_id: str | None = None
    worker_id: str | None = None

    if subject_type == "work":
        work_id = subject_id
    elif subject_type == "worker":
        worker_id = subject_id

    if details:
        work_id = details.get("work_id", work_id)
        worker_id = details.get("worker_id", worker_id)

    return work_id, worker_id


def list_events(conn: sqlite3.Connection, limit: int = 100) -> list:
    from nexus.models import EventRecord

    rows = conn.execute(
        "SELECT * FROM events ORDER BY id DESC LIMIT ?",
        (limit,),
    ).fetchall()

    events: list[EventRecord] = []
    for row in rows:
        details = json.loads(row["details"]) if row["details"] else None
        work_id, worker_id = _extract_ids(row["subject_type"], row["subject_id"], details)
        events.append(
            EventRecord(
                id=row["id"],
                timestamp=row["timestamp"],
                event_type=row["event_type"],
                action=row["action"],
                work_id=work_id,
                worker_id=worker_id,
                subject_type=row["subject_type"],
                subject_id=row["subject_id"],
                reason=row["reason"],
                details=details,
            )
        )
    return events
