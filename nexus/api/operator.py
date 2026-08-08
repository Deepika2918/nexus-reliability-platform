"""Read-only operator dashboard API."""

import sqlite3

from fastapi import APIRouter, Depends, Query

from nexus.database import get_db
from nexus.models import EventRecord, OperatorSnapshot, OperatorSummary, WorkOverviewItem, WorkerOverviewItem
from nexus.services.events import list_events
from nexus.services.operator import (
    get_operator_snapshot,
    get_summary,
    get_work_overview,
    get_workers_overview,
)

router = APIRouter(prefix="/api/operator", tags=["operator"])


def db_conn() -> sqlite3.Connection:
    return get_db()


@router.get("/summary", response_model=OperatorSummary)
def operator_summary(conn=Depends(db_conn)) -> OperatorSummary:
    return get_summary(conn)


@router.get("/work", response_model=list[WorkOverviewItem])
def operator_work(conn=Depends(db_conn)) -> list[WorkOverviewItem]:
    return get_work_overview(conn)


@router.get("/workers", response_model=list[WorkerOverviewItem])
def operator_workers(conn=Depends(db_conn)) -> list[WorkerOverviewItem]:
    return get_workers_overview(conn)


@router.get("/events", response_model=list[EventRecord])
def operator_events(
    limit: int = Query(default=100, ge=1, le=500),
    conn=Depends(db_conn),
) -> list[EventRecord]:
    return list_events(conn, limit=limit)


@router.get("/snapshot", response_model=OperatorSnapshot)
def operator_snapshot(
    event_limit: int = Query(default=100, ge=1, le=500),
    conn=Depends(db_conn),
) -> OperatorSnapshot:
    return get_operator_snapshot(conn, event_limit=event_limit)
