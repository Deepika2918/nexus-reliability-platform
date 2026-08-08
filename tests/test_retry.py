"""Verify retry, lease recovery, and dead-letter behaviour (Phase 4)."""

import pytest
from fastapi.testclient import TestClient

from nexus.config import Settings
from nexus.database import get_db, reset_db_connection
from nexus.main import create_app
from nexus.services.events import list_event_actions
from nexus.services.retry import compute_backoff_seconds
from tests.conftest import patch_settings


@pytest.fixture
def worker_client(client):
    client.post("/api/workers/register", json={"id": "worker-1"})
    return client


@pytest.fixture
def small_retry_client(tmp_path, monkeypatch):
    test_settings = Settings(
        database_path=tmp_path / "retry.db",
        recovery_loop_enabled=False,
        max_work_attempts=3,
        lease_seconds=10,
        retry_base_seconds=2,
        retry_max_seconds=300,
    )
    patch_settings(monkeypatch, test_settings)
    reset_db_connection()
    app = create_app()
    with TestClient(app) as c:
        c.post("/api/workers/register", json={"id": "worker-1"})
        yield c
    reset_db_connection()


def _submit_poll_fail(client, work_id: str, error: str = "boom") -> None:
    client.post("/api/work", json={"id": work_id, "type": "echo", "body": {"n": 1}})
    client.post("/api/workers/worker-1/poll")
    client.post(
        f"/api/work/{work_id}/fail",
        json={"worker_id": "worker-1", "error": error},
    )


def _exhaust_retries(client, work_id: str, fake_clock, attempts: int = 3) -> None:
    client.post("/api/work", json={"id": work_id, "type": "echo", "body": {}})
    for _ in range(attempts):
        client.post("/api/workers/worker-1/poll")
        client.post(
            f"/api/work/{work_id}/fail",
            json={"worker_id": "worker-1", "error": "fail again"},
        )
        fake_clock.advance(10)
        client.post("/api/system/recovery")


def test_failed_work_enters_retry_flow(worker_client):
    _submit_poll_fail(worker_client, "retry-1")

    work = worker_client.get("/api/work/retry-1").json()
    assert work["status"] == "RETRY_WAIT"
    assert work["last_error"] == "boom"
    assert work["next_retry_at"] is not None
    assert work["assigned_worker_id"] is None


def test_retry_count_increases_on_repoll(small_retry_client, fake_clock):
    small_retry_client.post("/api/work", json={"id": "count-1", "type": "echo", "body": {}})
    small_retry_client.post("/api/workers/worker-1/poll")
    assert small_retry_client.get("/api/work/count-1").json()["attempt_count"] == 1

    small_retry_client.post(
        "/api/work/count-1/fail",
        json={"worker_id": "worker-1", "error": "first fail"},
    )
    fake_clock.advance(3)
    small_retry_client.post("/api/system/recovery")

    small_retry_client.post("/api/workers/worker-1/poll")
    assert small_retry_client.get("/api/work/count-1").json()["attempt_count"] == 2


def test_retry_backoff_is_applied(worker_client):
    _submit_poll_fail(worker_client, "backoff-1")
    work = worker_client.get("/api/work/backoff-1").json()
    assert compute_backoff_seconds(work["attempt_count"]) == 2
    assert work["next_retry_at"] is not None


def test_work_can_succeed_after_retry(worker_client, fake_clock):
    _submit_poll_fail(worker_client, "success-1", error="temporary")

    fake_clock.advance(3)
    worker_client.post("/api/system/recovery")

    poll = worker_client.post("/api/workers/worker-1/poll")
    assert poll.status_code == 200
    assert poll.json()["status"] == "PROCESSING"

    done = worker_client.post(
        "/api/work/success-1/complete",
        json={"worker_id": "worker-1", "result": {"ok": True}},
    )
    assert done.status_code == 200
    assert done.json()["status"] == "COMPLETED"


def test_retry_limit_moves_to_failed(small_retry_client, fake_clock):
    work_id = "limit-1"
    _exhaust_retries(small_retry_client, work_id, fake_clock, attempts=3)

    work = small_retry_client.get(f"/api/work/{work_id}").json()
    assert work["status"] == "FAILED"
    assert work["attempt_count"] == 3
    assert "fail again" in work["last_error"]


def test_failed_work_is_not_retried_again(small_retry_client, fake_clock):
    work_id = "no-more-retries"
    _exhaust_retries(small_retry_client, work_id, fake_clock, attempts=3)

    fake_clock.advance(1000)
    small_retry_client.post("/api/system/recovery")
    poll = small_retry_client.post("/api/workers/worker-1/poll")
    assert poll.status_code == 204

    failed = small_retry_client.get("/api/work", params={"status": "FAILED"}).json()
    assert len(failed) == 1
    assert failed[0]["id"] == work_id


def test_retry_state_survives_restart(tmp_path, monkeypatch, fake_clock):
    db_path = tmp_path / "retry_restart.db"
    test_settings = Settings(
        database_path=db_path,
        recovery_loop_enabled=False,
        max_work_attempts=5,
    )
    monkeypatch.setattr("nexus.config.settings", test_settings)
    monkeypatch.setattr("nexus.database.settings", test_settings)
    patch_settings(monkeypatch, test_settings)

    reset_db_connection()
    app1 = create_app()
    with TestClient(app1) as client1:
        client1.post("/api/workers/register", json={"id": "worker-1"})
        client1.post("/api/work", json={"id": "persist-retry", "type": "echo", "body": {}})
        client1.post("/api/workers/worker-1/poll")
        client1.post(
            "/api/work/persist-retry/fail",
            json={"worker_id": "worker-1", "error": "survive"},
        )
        before = client1.get("/api/work/persist-retry").json()

    reset_db_connection()
    app2 = create_app()
    with TestClient(app2) as client2:
        after = client2.get("/api/work/persist-retry").json()

    assert before["status"] == "RETRY_WAIT"
    assert after["status"] == "RETRY_WAIT"
    assert after["attempt_count"] == before["attempt_count"]
    assert after["next_retry_at"] == before["next_retry_at"]
    assert after["last_error"] == "survive"


def test_retry_events_recorded(small_retry_client, fake_clock):
    work_id = "events-1"
    small_retry_client.post("/api/work", json={"id": work_id, "type": "echo", "body": {}})
    small_retry_client.post("/api/workers/worker-1/poll")
    small_retry_client.post(
        f"/api/work/{work_id}/fail",
        json={"worker_id": "worker-1", "error": "err"},
    )

    actions = list_event_actions(get_db(), work_id)
    assert "worker_failure" in actions
    assert "retry_scheduled" in actions

    fake_clock.advance(10)
    small_retry_client.post("/api/system/recovery")
    actions_after = list_event_actions(get_db(), work_id)
    assert "retry_attempt" in actions_after


def test_exhaustion_events_recorded(small_retry_client, fake_clock):
    work_id = "events-fail"
    _exhaust_retries(small_retry_client, work_id, fake_clock, attempts=3)

    actions = list_event_actions(get_db(), work_id)
    assert "retry_exhausted" in actions
    assert "permanently_failed" in actions


def test_lease_expiration_moves_to_retry_wait(tmp_path, monkeypatch, fake_clock):
    test_settings = Settings(
        database_path=tmp_path / "lease.db",
        recovery_loop_enabled=False,
        lease_seconds=5,
        max_work_attempts=5,
    )
    monkeypatch.setattr("nexus.config.settings", test_settings)
    monkeypatch.setattr("nexus.database.settings", test_settings)
    patch_settings(monkeypatch, test_settings)
    reset_db_connection()
    app = create_app()
    with TestClient(app) as client:
        client.post("/api/workers/register", json={"id": "worker-1"})
        client.post("/api/work", json={"id": "lease-1", "type": "echo", "body": {}})
        client.post("/api/workers/worker-1/poll")
        assert client.get("/api/work/lease-1").json()["status"] == "PROCESSING"

        fake_clock.advance(6)
        client.post("/api/system/recovery")

        work = client.get("/api/work/lease-1").json()
        assert work["status"] == "RETRY_WAIT"
        assert work["last_error"] is not None
        assert "lease_expired" in list_event_actions(get_db(), "lease-1")

    reset_db_connection()


def test_simulated_fail_on_claim(worker_client):
    worker_client.post(
        "/api/simulate/workers/worker-1/failure-mode",
        json={"mode": "fail_on_claim"},
    )
    worker_client.post("/api/work", json={"id": "sim-fail", "type": "echo", "body": {}})

    poll = worker_client.post("/api/workers/worker-1/poll")
    assert poll.status_code == 200
    assert poll.json()["status"] == "RETRY_WAIT"

    worker_client.post(
        "/api/simulate/workers/worker-1/failure-mode",
        json={"mode": "normal"},
    )


def test_compute_backoff_is_deterministic():
    assert compute_backoff_seconds(1) == 2
    assert compute_backoff_seconds(2) == 4
    assert compute_backoff_seconds(10) == 300
