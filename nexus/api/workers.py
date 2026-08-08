"""Worker registration and polling endpoints."""

import sqlite3

from fastapi import APIRouter, Depends, HTTPException, Response

from nexus.database import get_db
from nexus.models import WorkerRegisterRequest, WorkerResponse, WorkResponse
from nexus.services.work import poll_and_claim_work
from nexus.services.workers import (
    WorkerNotFoundError,
    WorkerUnavailableError,
    get_worker,
    register_worker,
)

router = APIRouter(prefix="/api/workers", tags=["workers"])


def db_conn() -> sqlite3.Connection:
    return get_db()


@router.post("/register", response_model=WorkerResponse)
def register_worker_identity(
    payload: WorkerRegisterRequest,
    response: Response,
    conn=Depends(db_conn),
) -> WorkerResponse:
    worker, created = register_worker(conn, payload.id)
    response.status_code = 201 if created else 200
    return worker


@router.get("/{worker_id}", response_model=WorkerResponse)
def get_worker_identity(worker_id: str, conn=Depends(db_conn)) -> WorkerResponse:
    worker = get_worker(conn, worker_id)
    if worker is None:
        raise HTTPException(status_code=404, detail=f"Worker '{worker_id}' not found")
    return worker


@router.post("/{worker_id}/poll", response_model=WorkResponse | None)
def poll_for_work(worker_id: str, response: Response, conn=Depends(db_conn)) -> WorkResponse | None:
    try:
        work = poll_and_claim_work(conn, worker_id)
    except WorkerNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except WorkerUnavailableError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    if work is None:
        response.status_code = 204
        return None
    return work
