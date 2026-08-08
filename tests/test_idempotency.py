# Placeholder — implemented in Phase 5
"""Verify idempotent completion and safe re-delivery."""

import pytest
from fastapi.testclient import TestClient

from nexus.config import Settings
from nexus.database import get_connection, reset_db_connection
from nexus.main import create_app


@pytest.fixture
def idempotency_client(tmp_path, monkeypatch):
    test_settings = Settings(
        database_path=tmp_path / "idempotency.db",
        recovery_loop_enabled=False,
        lease_seconds=5,
        max_work_attempts=5,
    )

    monkeypatch.setattr("nexus.config.settings", test_settings)
    monkeypatch.setattr("nexus.database.settings", test_settings)

    reset_db_connection()

    app = create_app()

    with TestClient(app) as client:
        yield client

    reset_db_connection()


def test_duplicate_completion_is_idempotent(idempotency_client):
    client = idempotency_client

    client.post(
        "/api/work",
        json={
            "id": "idem-1",
            "type": "echo",
            "body": {"message": "hello"},
        },
    )

    client.post(
        "/api/workers/register",
        json={"id": "worker-1"},
    )

    poll = client.post("/api/workers/worker-1/poll")
    assert poll.status_code == 200
    assert poll.json()["status"] == "PROCESSING"

    first = client.post(
        "/api/work/idem-1/complete",
        json={
            "worker_id": "worker-1",
            "result": {"ok": True},
        },
    )

    assert first.status_code == 200
    assert first.json()["status"] == "COMPLETED"

    second = client.post(
        "/api/work/idem-1/complete",
        json={
            "worker_id": "worker-1",
            "result": {"ok": False},
        },
    )

    assert second.status_code == 200
    assert second.json()["status"] == "COMPLETED"

    conn = get_connection()
    completions = conn.execute(
        "SELECT * FROM completions WHERE work_id = ?",
        ("idem-1",),
    ).fetchall()

    events = conn.execute(
        """
        SELECT action
        FROM events
        WHERE subject_id = ?
        AND action = 'completed'
        """,
        ("idem-1",),
    ).fetchall()

    conn.close()

    # Duplicate completion must not create another completion record.
    assert len(completions) == 1

    # Duplicate completion must not create another completed event.
    assert len(events) == 1


def test_completed_work_can_be_safely_completed_again(idempotency_client):
    client = idempotency_client

    client.post(
        "/api/work",
        json={
            "id": "idem-2",
            "type": "echo",
            "body": {},
        },
    )

    client.post(
        "/api/workers/register",
        json={"id": "worker-1"},
    )

    client.post("/api/workers/worker-1/poll")

    completed = client.post(
        "/api/work/idem-2/complete",
        json={
            "worker_id": "worker-1",
            "result": {"value": 123},
        },
    )

    assert completed.status_code == 200
    assert completed.json()["status"] == "COMPLETED"

    # Same completion request again must remain successful and harmless.
    duplicate = client.post(
        "/api/work/idem-2/complete",
        json={
            "worker_id": "worker-1",
            "result": {"value": 999},
        },
    )

    assert duplicate.status_code == 200
    assert duplicate.json()["status"] == "COMPLETED"

    work = client.get("/api/work/idem-2").json()
    assert work["status"] == "COMPLETED"


def test_wrong_worker_cannot_complete_processing_work(idempotency_client):
    client = idempotency_client

    client.post(
        "/api/work",
        json={
            "id": "idem-3",
            "type": "echo",
            "body": {},
        },
    )

    client.post(
        "/api/workers/register",
        json={"id": "worker-1"},
    )

    client.post(
        "/api/workers/register",
        json={"id": "worker-2"},
    )

    client.post("/api/workers/worker-1/poll")

    wrong_worker = client.post(
        "/api/work/idem-3/complete",
        json={
            "worker_id": "worker-2",
            "result": {"wrong": True},
        },
    )

    assert wrong_worker.status_code == 409

    work = client.get("/api/work/idem-3").json()

    assert work["status"] == "PROCESSING"
    assert work["assigned_worker_id"] == "worker-1"


def test_duplicate_completion_does_not_change_original_result(
    idempotency_client,
):
    client = idempotency_client

    client.post(
        "/api/work",
        json={
            "id": "idem-4",
            "type": "echo",
            "body": {},
        },
    )

    client.post(
        "/api/workers/register",
        json={"id": "worker-1"},
    )

    client.post("/api/workers/worker-1/poll")

    client.post(
        "/api/work/idem-4/complete",
        json={
            "worker_id": "worker-1",
            "result": {"original": True},
        },
    )

    # A later duplicate must not overwrite the already recorded result.
    client.post(
        "/api/work/idem-4/complete",
        json={
            "worker_id": "worker-1",
            "result": {"original": False},
        },
    )

    conn = get_connection()
    row = conn.execute(
        "SELECT result, completion_count FROM completions WHERE work_id = ?",
        ("idem-4",),
    ).fetchone()
    conn.close()

    assert row is not None
    assert row["completion_count"] == 1
    assert '"original": true' in row["result"]