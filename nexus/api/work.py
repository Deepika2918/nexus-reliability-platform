"""Work submission, completion, failure, and status endpoints."""

import sqlite3

from fastapi import APIRouter, Depends, HTTPException, Response

from nexus.database import get_db
from nexus.models import (
    WorkCompleteRequest,
    WorkFailRequest,
    WorkResponse,
    WorkStatus,
    WorkSubmitRequest,
)
from nexus.services.work import (
    WorkAssignmentError,
    WorkNotFoundError,
    WorkStateError,
    accept_work,
    complete_work,
    fail_work,
    get_work,
    list_work,
)

router = APIRouter(prefix="/api/work", tags=["work"])


def db_conn() -> sqlite3.Connection:
    return get_db()


@router.post("", response_model=WorkResponse)
def submit_work(payload: WorkSubmitRequest, response: Response, conn=Depends(db_conn)) -> WorkResponse:
    result = accept_work(
        conn,
        work_id=payload.id,
        work_type=payload.type,
        body=payload.body,
    )
    response.status_code = 202 if result.created else 200
    return result.work


@router.get("", response_model=list[WorkResponse])
def get_work_list(status: WorkStatus | None = None, conn=Depends(db_conn)) -> list[WorkResponse]:
    return list_work(conn, status=status)


@router.post("/{work_id}/complete", response_model=WorkResponse)
def complete_work_item(work_id: str, payload: WorkCompleteRequest, conn=Depends(db_conn)) -> WorkResponse:
    try:
        return complete_work(
            conn,
            work_id=work_id,
            worker_id=payload.worker_id,
            result=payload.result,
        )
    except WorkNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except WorkAssignmentError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except WorkStateError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/{work_id}/fail", response_model=WorkResponse)
def fail_work_item(work_id: str, payload: WorkFailRequest, conn=Depends(db_conn)) -> WorkResponse:
    try:
        return fail_work(
            conn,
            work_id=work_id,
            worker_id=payload.worker_id,
            error=payload.error,
        )
    except WorkNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except WorkAssignmentError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except WorkStateError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/{work_id}", response_model=WorkResponse)
def get_work_by_id(work_id: str, conn=Depends(db_conn)) -> WorkResponse:
    work = get_work(conn, work_id)
    if work is None:
        raise HTTPException(status_code=404, detail=f"Work '{work_id}' not found")
    return work
