"""Work acceptance, dispatch, and completion."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from nexus.clock import clock
from nexus.config import settings
from nexus.models import FailureMode, WorkResponse, WorkStatus
from nexus.services.events import record_event
from nexus.services.retry import handle_work_failure, run_recovery_cycle
from nexus.services.workers import ensure_worker_can_poll, get_worker


class WorkError(Exception):
    """Base work service error."""


class WorkNotFoundError(WorkError):
    pass


class WorkStateError(WorkError):
    pass


class WorkAssignmentError(WorkError):
    pass


@dataclass(frozen=True)
class AcceptResult:
    work: WorkResponse
    created: bool


def _lease_expires_at() -> str:
    expires = datetime.fromtimestamp(
        clock.now() + settings.lease_seconds,
        tz=timezone.utc,
    )
    return expires.isoformat()


def _row_to_work(row: sqlite3.Row) -> WorkResponse:
    return WorkResponse(
        id=row["id"],
        type=row["type"],
        body=json.loads(row["body"]),
        status=WorkStatus(row["status"]),
        attempt_count=row["attempt_count"],
        max_attempts=row["max_attempts"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        accepted_at=row["accepted_at"],
        next_retry_at=row["next_retry_at"],
        assigned_worker_id=row["assigned_worker_id"],
        lease_expires_at=row["lease_expires_at"],
        last_error=row["last_error"],
        completed_at=row["completed_at"],
    )


def get_work(conn: sqlite3.Connection, work_id: str) -> WorkResponse | None:
    row = conn.execute("SELECT * FROM works WHERE id = ?", (work_id,)).fetchone()
    if row is None:
        return None
    return _row_to_work(row)


def list_work(conn: sqlite3.Connection, status: WorkStatus | None = None) -> list[WorkResponse]:
    if status is None:
        rows = conn.execute("SELECT * FROM works ORDER BY created_at ASC").fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM works WHERE status = ? ORDER BY created_at ASC",
            (status.value,),
        ).fetchall()
    return [_row_to_work(row) for row in rows]


def accept_work(
    conn: sqlite3.Connection,
    *,
    work_id: str,
    work_type: str,
    body: dict[str, Any],
) -> AcceptResult:
    existing = get_work(conn, work_id)
    if existing is not None:
        record_event(
            conn,
            event_type="work",
            subject_type="work",
            subject_id=work_id,
            action="duplicate_accept",
            reason="Work with this id was already accepted; returning existing record.",
            details={"status": existing.status.value},
        )
        conn.commit()
        return AcceptResult(work=existing, created=False)

    now = clock.iso_now()
    conn.execute(
        """
        INSERT INTO works (
            id, type, body, status, attempt_count, max_attempts,
            created_at, updated_at, accepted_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            work_id,
            work_type,
            json.dumps(body),
            WorkStatus.ACCEPTED.value,
            0,
            settings.max_work_attempts,
            now,
            now,
            now,
        ),
    )
    record_event(
        conn,
        event_type="work",
        subject_type="work",
        subject_id=work_id,
        action="accepted",
        reason="Work accepted and persisted before acknowledgement.",
        details={"type": work_type},
    )
    conn.commit()

    work = get_work(conn, work_id)
    assert work is not None
    return AcceptResult(work=work, created=True)


def poll_and_claim_work(conn: sqlite3.Connection, worker_id: str) -> WorkResponse | None:
    """Atomically claim the oldest ACCEPTED work item for a registered worker."""
    run_recovery_cycle(conn)
    ensure_worker_can_poll(conn, worker_id)

    conn.execute("BEGIN IMMEDIATE")
    try:
        row = conn.execute(
            """
            SELECT id FROM works
            WHERE status = ?
            ORDER BY created_at ASC
            LIMIT 1
            """,
            (WorkStatus.ACCEPTED.value,),
        ).fetchone()
        if row is None:
            conn.commit()
            return None

        work_id = row["id"]
        now = clock.iso_now()
        lease_expires = _lease_expires_at()
        cursor = conn.execute(
            """
            UPDATE works
            SET status = ?, assigned_worker_id = ?, lease_expires_at = ?,
                attempt_count = attempt_count + 1, updated_at = ?
            WHERE id = ? AND status = ?
            """,
            (
                WorkStatus.PROCESSING.value,
                worker_id,
                lease_expires,
                now,
                work_id,
                WorkStatus.ACCEPTED.value,
            ),
        )
        if cursor.rowcount != 1:
            conn.commit()
            return None

        record_event(
            conn,
            event_type="work",
            subject_type="work",
            subject_id=work_id,
            action="dispatched",
            reason="Work dispatched to worker for processing.",
            details={"worker_id": worker_id, "attempt_count": _attempt_count(conn, work_id)},
        )
        record_event(
            conn,
            event_type="work",
            subject_type="work",
            subject_id=work_id,
            action="processing",
            reason="Work is now being processed by the assigned worker.",
            details={"worker_id": worker_id, "lease_expires_at": lease_expires},
        )

        worker = get_worker(conn, worker_id)
        if worker is not None and worker.failure_mode == FailureMode.FAIL_ON_CLAIM:
            handle_work_failure(
                conn,
                work_id=work_id,
                reason="Simulated worker failure on claim.",
                worker_id=worker_id,
                failure_action="worker_failure",
            )

        conn.commit()
        return get_work(conn, work_id)
    except Exception:
        conn.rollback()
        raise


def _attempt_count(conn: sqlite3.Connection, work_id: str) -> int:
    row = conn.execute("SELECT attempt_count FROM works WHERE id = ?", (work_id,)).fetchone()
    return int(row["attempt_count"]) if row else 0


def complete_work(
    conn: sqlite3.Connection,
    *,
    work_id: str,
    worker_id: str,
    result: dict[str, Any],
) -> WorkResponse:
    conn.execute("BEGIN IMMEDIATE")
    try:
        row = conn.execute("SELECT * FROM works WHERE id = ?", (work_id,)).fetchone()
        if row is None:
            raise WorkNotFoundError(f"Work '{work_id}' not found")

        if row["status"] == WorkStatus.COMPLETED.value:
            conn.commit()
            return _row_to_work(row)

        if row["status"] != WorkStatus.PROCESSING.value:
            raise WorkStateError(
                f"Work '{work_id}' cannot be completed from status {row['status']}"
            )
        if row["assigned_worker_id"] != worker_id:
            raise WorkAssignmentError(
                f"Work '{work_id}' is assigned to '{row['assigned_worker_id']}', not '{worker_id}'"
            )

        now = clock.iso_now()
        conn.execute(
            """
            UPDATE works
            SET status = ?, completed_at = ?, updated_at = ?,
                assigned_worker_id = ?, lease_expires_at = NULL
            WHERE id = ?
            """,
            (WorkStatus.COMPLETED.value, now, now, worker_id, work_id),
        )
        conn.execute(
            """
            INSERT INTO completions (work_id, result, completed_at, completion_count)
            VALUES (?, ?, ?, 1)
            """,
            (work_id, json.dumps(result), now),
        )
        record_event(
            conn,
            event_type="work",
            subject_type="work",
            subject_id=work_id,
            action="completed",
            reason="Work completed successfully by assigned worker.",
            details={"worker_id": worker_id, "result": result},
        )
        conn.commit()
        work = get_work(conn, work_id)
        assert work is not None
        return work
    except WorkError:
        conn.rollback()
        raise
    except Exception:
        conn.rollback()
        raise


def fail_work(
    conn: sqlite3.Connection,
    *,
    work_id: str,
    worker_id: str,
    error: str,
) -> WorkResponse:
    conn.execute("BEGIN IMMEDIATE")
    try:
        row = conn.execute("SELECT * FROM works WHERE id = ?", (work_id,)).fetchone()
        if row is None:
            raise WorkNotFoundError(f"Work '{work_id}' not found")
        if row["status"] != WorkStatus.PROCESSING.value:
            raise WorkStateError(
                f"Work '{work_id}' cannot fail from status {row['status']}"
            )
        if row["assigned_worker_id"] != worker_id:
            raise WorkAssignmentError(
                f"Work '{work_id}' is assigned to '{row['assigned_worker_id']}', not '{worker_id}'"
            )

        handle_work_failure(
            conn,
            work_id=work_id,
            reason=error,
            worker_id=worker_id,
            failure_action="worker_failure",
        )
        conn.commit()
        work = get_work(conn, work_id)
        assert work is not None
        return work
    except WorkError:
        conn.rollback()
        raise
    except Exception:
        conn.rollback()
        raise
