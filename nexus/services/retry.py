"""Retry backoff and dead-letter transitions."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone

from nexus.clock import clock
from nexus.config import settings
from nexus.models import WorkStatus
from nexus.services.events import record_event


def compute_backoff_seconds(attempt_count: int) -> int:
    """Exponential backoff capped at settings.retry_max_seconds."""
    delay = settings.retry_base_seconds**attempt_count
    return int(min(settings.retry_max_seconds, delay))


def _iso_to_timestamp(iso_value: str) -> float:
    return datetime.fromisoformat(iso_value).timestamp()


def _future_iso(seconds_from_now: int) -> str:
    return datetime.fromtimestamp(clock.now() + seconds_from_now, tz=timezone.utc).isoformat()


def handle_work_failure(
    conn: sqlite3.Connection,
    *,
    work_id: str,
    reason: str,
    worker_id: str | None = None,
    failure_action: str = "worker_failure",
) -> None:
    """Move failed in-flight work to RETRY_WAIT or FAILED depending on attempt budget."""
    row = conn.execute("SELECT * FROM works WHERE id = ?", (work_id,)).fetchone()
    if row is None:
        return
    if row["status"] != WorkStatus.PROCESSING.value:
        return

    attempt_count = int(row["attempt_count"])
    max_attempts = int(row["max_attempts"])
    now = clock.iso_now()

    if worker_id:
        record_event(
            conn,
            event_type="worker",
            subject_type="worker",
            subject_id=worker_id,
            action="worker_failure",
            reason=f"Worker reported failure while processing work '{work_id}'.",
            details={"work_id": work_id, "error": reason},
        )

    if failure_action == "lease_expired":
        record_event(
            conn,
            event_type="work",
            subject_type="work",
            subject_id=work_id,
            action="lease_expired",
            reason=reason,
            details={"worker_id": row["assigned_worker_id"], "attempt_count": attempt_count},
        )
    elif failure_action == "worker_failure":
        record_event(
            conn,
            event_type="work",
            subject_type="work",
            subject_id=work_id,
            action="worker_failure",
            reason=reason,
            details={"worker_id": worker_id, "attempt_count": attempt_count},
        )

    if attempt_count >= max_attempts:
        conn.execute(
            """
            UPDATE works
            SET status = ?, last_error = ?, updated_at = ?,
                assigned_worker_id = NULL, lease_expires_at = NULL, next_retry_at = NULL
            WHERE id = ?
            """,
            (WorkStatus.FAILED.value, reason, now, work_id),
        )
        record_event(
            conn,
            event_type="work",
            subject_type="work",
            subject_id=work_id,
            action="retry_exhausted",
            reason="Maximum retry attempts reached; no further retries will be scheduled.",
            details={"attempt_count": attempt_count, "max_attempts": max_attempts},
        )
        record_event(
            conn,
            event_type="work",
            subject_type="work",
            subject_id=work_id,
            action="permanently_failed",
            reason="Work moved to FAILED dead-letter state.",
            details={"last_error": reason},
        )
        return

    delay_seconds = compute_backoff_seconds(attempt_count)
    next_retry_at = _future_iso(delay_seconds)
    conn.execute(
        """
        UPDATE works
        SET status = ?, last_error = ?, updated_at = ?,
            next_retry_at = ?, assigned_worker_id = NULL, lease_expires_at = NULL
        WHERE id = ?
        """,
        (WorkStatus.RETRY_WAIT.value, reason, now, next_retry_at, work_id),
    )
    record_event(
        conn,
        event_type="work",
        subject_type="work",
        subject_id=work_id,
        action="retry_scheduled",
        reason="Work scheduled for retry after backoff delay.",
        details={
            "attempt_count": attempt_count,
            "max_attempts": max_attempts,
            "delay_seconds": delay_seconds,
            "next_retry_at": next_retry_at,
        },
    )


def recover_expired_leases(conn: sqlite3.Connection) -> int:
    """Detect abandoned PROCESSING work using lease_expires_at."""
    rows = conn.execute(
        """
        SELECT id, lease_expires_at, assigned_worker_id
        FROM works
        WHERE status = ? AND lease_expires_at IS NOT NULL
        """,
        (WorkStatus.PROCESSING.value,),
    ).fetchall()

    recovered = 0
    now_ts = clock.now()
    for row in rows:
        if _iso_to_timestamp(row["lease_expires_at"]) > now_ts:
            continue
        handle_work_failure(
            conn,
            work_id=row["id"],
            reason="Processing lease expired before work was completed.",
            worker_id=row["assigned_worker_id"],
            failure_action="lease_expired",
        )
        recovered += 1
    return recovered


def promote_due_retries(conn: sqlite3.Connection) -> int:
    """Promote RETRY_WAIT work whose backoff has elapsed back to ACCEPTED."""
    rows = conn.execute(
        """
        SELECT id, next_retry_at, attempt_count
        FROM works
        WHERE status = ? AND next_retry_at IS NOT NULL
        """,
        (WorkStatus.RETRY_WAIT.value,),
    ).fetchall()

    promoted = 0
    now_ts = clock.now()
    now_iso = clock.iso_now()
    for row in rows:
        if _iso_to_timestamp(row["next_retry_at"]) > now_ts:
            continue
        conn.execute(
            """
            UPDATE works
            SET status = ?, next_retry_at = NULL, updated_at = ?
            WHERE id = ? AND status = ?
            """,
            (WorkStatus.ACCEPTED.value, now_iso, row["id"], WorkStatus.RETRY_WAIT.value),
        )
        record_event(
            conn,
            event_type="work",
            subject_type="work",
            subject_id=row["id"],
            action="retry_attempt",
            reason="Retry backoff elapsed; work is eligible for dispatch again.",
            details={"attempt_count": row["attempt_count"]},
        )
        promoted += 1
    return promoted


def run_recovery_cycle(conn: sqlite3.Connection) -> dict[str, int]:
    conn.execute("BEGIN IMMEDIATE")
    try:
        expired = recover_expired_leases(conn)
        promoted = promote_due_retries(conn)
        conn.commit()
        return {"expired_leases": expired, "promoted_retries": promoted}
    except Exception:
        conn.rollback()
        raise
