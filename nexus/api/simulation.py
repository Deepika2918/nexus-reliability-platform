"""Deliberate failure injection for reviewers."""

import sqlite3

from fastapi import APIRouter, Depends, HTTPException

from nexus.database import get_db
from nexus.models import FailureModeRequest, WorkerResponse
from nexus.services.retry import run_recovery_cycle
from nexus.services.workers import WorkerNotFoundError, set_worker_failure_mode

router = APIRouter(prefix="/api/simulate", tags=["simulation"])


def db_conn() -> sqlite3.Connection:
    return get_db()


@router.post("/workers/{worker_id}/failure-mode", response_model=WorkerResponse)
def simulate_worker_failure_mode(
    worker_id: str,
    payload: FailureModeRequest,
    conn=Depends(db_conn),
) -> WorkerResponse:
    try:
        return set_worker_failure_mode(conn, worker_id, payload.mode)
    except WorkerNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/recovery/run")
def run_recovery(conn=Depends(db_conn)) -> dict[str, int]:
    """Manually run lease recovery and retry promotion (for demos/tests)."""
    return run_recovery_cycle(conn)
