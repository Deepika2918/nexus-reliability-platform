"""Read-only operator dashboard queries."""

from __future__ import annotations

import json
import sqlite3

from nexus.models import (
    EventRecord,
    OperatorSnapshot,
    OperatorSummary,
    WorkOverviewItem,
    WorkerOverviewItem,
    WorkStatus,
    WorkerStatus,
)
from nexus.services.events import list_events
from nexus.services.work import list_work
from nexus.services.workers import list_workers


def _work_priority(body: dict) -> str:
    value = body.get("priority")
    if value is None:
        return "normal"
    return str(value)


def _work_to_overview(work) -> WorkOverviewItem:
    return WorkOverviewItem(
        id=work.id,
        type=work.type,
        status=work.status,
        priority=_work_priority(work.body),
        attempt_count=work.attempt_count,
        max_attempts=work.max_attempts,
        assigned_worker_id=work.assigned_worker_id,
        created_at=work.created_at,
        lease_expires_at=work.lease_expires_at,
        next_retry_at=work.next_retry_at,
        failure_reason=work.last_error,
    )


def _build_health(counts: dict[str, int]) -> tuple[str, str]:
    failed = counts.get(WorkStatus.FAILED.value, 0)
    retry_wait = counts.get(WorkStatus.RETRY_WAIT.value, 0)
    processing = counts.get(WorkStatus.PROCESSING.value, 0)
    accepted = counts.get(WorkStatus.ACCEPTED.value, 0)

    if failed > 0:
        return (
            "attention",
            f"{failed} work item(s) permanently failed and need operator review.",
        )
    if retry_wait > 0:
        return (
            "degraded",
            f"{retry_wait} work item(s) are waiting to retry after failures.",
        )
    if processing > 0:
        return (
            "ok",
            f"{processing} work item(s) currently processing; {accepted} queued.",
        )
    if accepted > 0:
        return ("ok", f"{accepted} work item(s) queued and waiting for workers.")
    return ("ok", "Platform is idle with no pending work.")


def get_summary(conn: sqlite3.Connection) -> OperatorSummary:
    rows = conn.execute(
        "SELECT status, COUNT(*) AS count FROM works GROUP BY status"
    ).fetchall()
    counts = {row["status"]: int(row["count"]) for row in rows}
    worker_count = conn.execute("SELECT COUNT(*) AS count FROM workers").fetchone()
    registered_workers = int(worker_count["count"]) if worker_count else 0

    total_work = sum(counts.values())
    health, health_detail = _build_health(counts)

    return OperatorSummary(
        total_work=total_work,
        accepted=counts.get(WorkStatus.ACCEPTED.value, 0),
        processing=counts.get(WorkStatus.PROCESSING.value, 0),
        retry_wait=counts.get(WorkStatus.RETRY_WAIT.value, 0),
        completed=counts.get(WorkStatus.COMPLETED.value, 0),
        failed=counts.get(WorkStatus.FAILED.value, 0),
        registered_workers=registered_workers,
        health=health,
        health_detail=health_detail,
    )


def get_work_overview(conn: sqlite3.Connection) -> list[WorkOverviewItem]:
    return [_work_to_overview(work) for work in list_work(conn)]


def get_workers_overview(conn: sqlite3.Connection) -> list[WorkerOverviewItem]:
    active = conn.execute(
        """
        SELECT id, assigned_worker_id, lease_expires_at
        FROM works
        WHERE status = ? AND assigned_worker_id IS NOT NULL
        """,
        (WorkStatus.PROCESSING.value,),
    ).fetchall()
    work_by_worker = {
        row["assigned_worker_id"]: {
            "work_id": row["id"],
            "lease_expires_at": row["lease_expires_at"],
        }
        for row in active
    }

    overview: list[WorkerOverviewItem] = []
    for worker in list_workers(conn):
        current = work_by_worker.get(worker.id)
        overview.append(
            WorkerOverviewItem(
                id=worker.id,
                status=worker.status,
                current_work_id=current["work_id"] if current else None,
                last_heartbeat_at=worker.last_heartbeat_at,
                last_activity_at=worker.updated_at,
                lease_expires_at=current["lease_expires_at"] if current else None,
                failure_mode=worker.failure_mode.value,
                restart_count=worker.restart_count,
                max_restarts=worker.max_restarts,
            )
        )
    return overview


def get_operator_snapshot(conn: sqlite3.Connection, *, event_limit: int = 100) -> OperatorSnapshot:
    return OperatorSnapshot(
        summary=get_summary(conn),
        work=get_work_overview(conn),
        workers=get_workers_overview(conn),
        events=list_events(conn, limit=event_limit),
    )
