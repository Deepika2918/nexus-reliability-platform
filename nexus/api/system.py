"""System maintenance endpoints."""

import sqlite3

from fastapi import APIRouter, Depends

from nexus.database import get_db
from nexus.services.retry import run_recovery_cycle

router = APIRouter(prefix="/api/system", tags=["system"])


def db_conn() -> sqlite3.Connection:
    return get_db()


@router.post("/recovery")
def trigger_recovery(conn=Depends(db_conn)) -> dict[str, int]:
    return run_recovery_cycle(conn)
