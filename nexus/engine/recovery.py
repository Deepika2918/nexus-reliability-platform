"""Background recovery loop helpers."""

from __future__ import annotations

import asyncio
import sqlite3

from nexus.config import settings
from nexus.services.retry import run_recovery_cycle


async def recovery_loop(get_connection_fn) -> None:
    while True:
        conn = get_connection_fn()
        run_recovery_cycle(conn)
        await asyncio.sleep(settings.recovery_loop_interval_seconds)
