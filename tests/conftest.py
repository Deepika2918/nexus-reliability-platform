"""Shared pytest fixtures."""

import pytest
from fastapi.testclient import TestClient

from nexus.config import Settings
from nexus.database import reset_db_connection
from nexus.main import create_app

SETTINGS_PATCH_TARGETS = (
    "nexus.config.settings",
    "nexus.database.settings",
    "nexus.services.work.settings",
    "nexus.services.workers.settings",
    "nexus.services.retry.settings",
    "nexus.engine.recovery.settings",
    "nexus.main.settings",
)


def patch_settings(monkeypatch, test_settings: Settings) -> None:
    for target in SETTINGS_PATCH_TARGETS:
        monkeypatch.setattr(target, test_settings)


@pytest.fixture
def client(tmp_path, monkeypatch):
    test_settings = Settings(
        database_path=tmp_path / "test.db",
        recovery_loop_enabled=False,
        lease_seconds=30,
        max_work_attempts=5,
    )
    patch_settings(monkeypatch, test_settings)
    reset_db_connection()
    app = create_app()
    with TestClient(app) as c:
        yield c
    reset_db_connection()


CLOCK_PATCH_TARGETS = (
    "nexus.clock.clock",
    "nexus.services.work.clock",
    "nexus.services.workers.clock",
    "nexus.services.retry.clock",
    "nexus.services.events.clock",
)


@pytest.fixture
def fake_clock(monkeypatch):
    class _FakeClock:
        def __init__(self) -> None:
            self.current = 1_700_000_000.0

        def now(self) -> float:
            return self.current

        def advance(self, seconds: float) -> None:
            self.current += seconds

    from nexus.clock import Clock

    state = _FakeClock()
    test_clock = Clock(now_fn=state.now)
    for target in CLOCK_PATCH_TARGETS:
        monkeypatch.setattr(target, test_clock)
    return state
