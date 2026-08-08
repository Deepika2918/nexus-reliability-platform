"""Worker registry, health, and recovery budget."""

from __future__ import annotations

import sqlite3

from nexus.clock import clock
from nexus.config import settings
from nexus.models import FailureMode, WorkerResponse, WorkerStatus
from nexus.services.events import record_event


class WorkerError(Exception):
    """Base worker service error."""


class WorkerNotFoundError(WorkerError):
    pass


class WorkerUnavailableError(WorkerError):
    pass


def _row_to_worker(row: sqlite3.Row) -> WorkerResponse:
    return WorkerResponse(
        id=row["id"],
        status=WorkerStatus(row["status"]),
        restart_count=row["restart_count"],
        max_restarts=row["max_restarts"],
        last_heartbeat_at=row["last_heartbeat_at"],
        failure_mode=FailureMode(row["failure_mode"]),
        release_version=row["release_version"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def get_worker(conn: sqlite3.Connection, worker_id: str) -> WorkerResponse | None:
    row = conn.execute("SELECT * FROM workers WHERE id = ?", (worker_id,)).fetchone()
    if row is None:
        return None
    return _row_to_worker(row)


def register_worker(conn: sqlite3.Connection, worker_id: str) -> tuple[WorkerResponse, bool]:
    """Register a worker identity. Returns (worker, created)."""
    existing = get_worker(conn, worker_id)
    now = clock.iso_now()

    if existing is not None:
        conn.execute(
            """
            UPDATE workers
            SET status = ?, last_heartbeat_at = ?, updated_at = ?
            WHERE id = ?
            """,
            (WorkerStatus.RUNNING.value, now, now, worker_id),
        )
        record_event(
            conn,
            event_type="worker",
            subject_type="worker",
            subject_id=worker_id,
            action="registered",
            reason="Existing worker re-registered and marked RUNNING.",
        )
        conn.commit()
        worker = get_worker(conn, worker_id)
        assert worker is not None
        return worker, False

    conn.execute(
        """
        INSERT INTO workers (
            id, status, restart_count, max_restarts, last_heartbeat_at,
            failure_mode, release_version, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            worker_id,
            WorkerStatus.RUNNING.value,
            0,
            settings.max_worker_restarts,
            now,
            FailureMode.NORMAL.value,
            "v1",
            now,
            now,
        ),
    )
    record_event(
        conn,
        event_type="worker",
        subject_type="worker",
        subject_id=worker_id,
        action="registered",
        reason="Worker registered and ready to poll for work.",
    )
    conn.commit()
    worker = get_worker(conn, worker_id)
    assert worker is not None
    return worker, True


def list_workers(conn: sqlite3.Connection) -> list[WorkerResponse]:
    rows = conn.execute("SELECT * FROM workers ORDER BY id ASC").fetchall()
    return [_row_to_worker(row) for row in rows]


def ensure_worker_can_poll(conn: sqlite3.Connection, worker_id: str) -> WorkerResponse:
    worker = get_worker(conn, worker_id)
    if worker is None:
        raise WorkerNotFoundError(f"Worker '{worker_id}' is not registered")
    if worker.status not in (WorkerStatus.RUNNING, WorkerStatus.SLOW):
        raise WorkerUnavailableError(
            f"Worker '{worker_id}' cannot poll while status is {worker.status.value}"
        )
    return worker


def set_worker_failure_mode(
    conn: sqlite3.Connection,
    worker_id: str,
    mode: FailureMode,
) -> WorkerResponse:
    worker = get_worker(conn, worker_id)
    if worker is None:
        raise WorkerNotFoundError(f"Worker '{worker_id}' is not registered")

    now = clock.iso_now()
    conn.execute(
        "UPDATE workers SET failure_mode = ?, updated_at = ? WHERE id = ?",
        (mode.value, now, worker_id),
    )
    record_event(
        conn,
        event_type="worker",
        subject_type="worker",
        subject_id=worker_id,
        action="failure_mode_set",
        reason=f"Worker failure simulation mode set to {mode.value}.",
        details={"mode": mode.value},
    )
    conn.commit()
    updated = get_worker(conn, worker_id)
    assert updated is not None
    return updated
