"""Verify dispatch, poll, and completion workflow (Phase 3)."""

import threading

import pytest

from nexus.config import Settings
from nexus.database import get_connection, init_db, reset_db_connection
from nexus.services.events import list_event_actions
from nexus.services.work import accept_work, poll_and_claim_work
from nexus.services.workers import register_worker


@pytest.fixture
def worker_client(client):
    client.post("/api/workers/register", json={"id": "worker-1"})
    return client


def test_worker_can_poll_accepted_work(worker_client):
    worker_client.post("/api/work", json={"id": "job-1", "type": "echo", "body": {"n": 1}})

    response = worker_client.post("/api/workers/worker-1/poll")

    assert response.status_code == 200
    work = response.json()
    assert work["id"] == "job-1"
    assert work["status"] == "PROCESSING"
    assert work["assigned_worker_id"] == "worker-1"
    assert work["body"] == {"n": 1}


def test_poll_changes_work_to_processing(worker_client):
    worker_client.post("/api/work", json={"id": "job-2", "type": "echo", "body": {}})

    worker_client.post("/api/workers/worker-1/poll")
    stored = worker_client.get("/api/work/job-2")

    assert stored.status_code == 200
    assert stored.json()["status"] == "PROCESSING"
    assert stored.json()["attempt_count"] == 1


def test_worker_can_complete_work(worker_client):
    worker_client.post("/api/work", json={"id": "job-3", "type": "echo", "body": {"x": "y"}})
    worker_client.post("/api/workers/worker-1/poll")

    response = worker_client.post(
        "/api/work/job-3/complete",
        json={"worker_id": "worker-1", "result": {"ok": True}},
    )

    assert response.status_code == 200
    work = response.json()
    assert work["status"] == "COMPLETED"
    assert work["completed_at"] is not None


def test_completed_work_is_not_dispatched_again(worker_client):
    worker_client.post("/api/work", json={"id": "job-4", "type": "echo", "body": {}})
    worker_client.post("/api/workers/worker-1/poll")
    worker_client.post(
        "/api/work/job-4/complete",
        json={"worker_id": "worker-1", "result": {"done": True}},
    )

    poll = worker_client.post("/api/workers/worker-1/poll")
    assert poll.status_code == 204

    listed = worker_client.get("/api/work", params={"status": "ACCEPTED"})
    assert listed.json() == []


def test_two_workers_cannot_claim_same_work(client):
    client.post("/api/workers/register", json={"id": "worker-a"})
    client.post("/api/workers/register", json={"id": "worker-b"})
    client.post("/api/work", json={"id": "shared-job", "type": "echo", "body": {}})

    first = client.post("/api/workers/worker-a/poll")
    second = client.post("/api/workers/worker-b/poll")

    statuses = sorted([first.status_code, second.status_code])
    assert statuses == [200, 204]

    claimed = first.json() if first.status_code == 200 else second.json()
    assert claimed["id"] == "shared-job"
    assert claimed["status"] == "PROCESSING"

    stored = client.get("/api/work/shared-job").json()
    assert stored["assigned_worker_id"] in {"worker-a", "worker-b"}


def test_concurrent_poll_claims_only_one_worker(tmp_path, monkeypatch):
    db_path = tmp_path / "concurrent.db"
    test_settings = Settings(database_path=db_path)
    monkeypatch.setattr("nexus.config.settings", test_settings)
    monkeypatch.setattr("nexus.database.settings", test_settings)
    reset_db_connection()

    conn = init_db(get_connection(db_path))
    register_worker(conn, "worker-a")
    register_worker(conn, "worker-b")
    accept_work(conn, work_id="race-job", work_type="echo", body={"race": True})
    conn.close()

    results: list[str | None] = []
    errors: list[Exception] = []

    def claim(worker_id: str) -> None:
        try:
            c = get_connection(db_path)
            work = poll_and_claim_work(c, worker_id)
            results.append(work.id if work else None)
            c.close()
        except Exception as exc:
            errors.append(exc)

    threads = [
        threading.Thread(target=claim, args=("worker-a",)),
        threading.Thread(target=claim, args=("worker-b",)),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert not errors
    assert len(results) == 2
    assert results.count("race-job") == 1
    assert results.count(None) == 1


def test_dispatch_and_completion_events_recorded(worker_client):
    worker_client.post("/api/work", json={"id": "job-ev", "type": "echo", "body": {}})
    worker_client.post("/api/workers/worker-1/poll")
    worker_client.post(
        "/api/work/job-ev/complete",
        json={"worker_id": "worker-1", "result": {"status": "ok"}},
    )

    from nexus.database import get_db

    actions = list_event_actions(get_db(), "job-ev")
    assert actions == ["accepted", "dispatched", "processing", "completed"]


def test_unregistered_worker_cannot_poll(client):
    client.post("/api/work", json={"id": "job-5", "type": "echo", "body": {}})

    response = client.post("/api/workers/unknown-worker/poll")

    assert response.status_code == 404


def test_wrong_worker_cannot_complete(worker_client):
    worker_client.post("/api/workers/register", json={"id": "worker-2"})
    worker_client.post("/api/work", json={"id": "job-6", "type": "echo", "body": {}})
    worker_client.post("/api/workers/worker-1/poll")

    response = worker_client.post(
        "/api/work/job-6/complete",
        json={"worker_id": "worker-2", "result": {"ok": True}},
    )

    assert response.status_code == 409
