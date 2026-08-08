"""Verify accepted work is persisted (R-01)."""

import pytest
from fastapi.testclient import TestClient

from nexus.config import Settings
from nexus.database import get_connection, reset_db_connection
from nexus.main import create_app
from nexus.services.work import get_work


@pytest.fixture(autouse=True)
def clean_db(tmp_path, monkeypatch):
    test_settings = Settings(database_path=tmp_path / "test.db")
    monkeypatch.setattr("nexus.config.settings", test_settings)
    monkeypatch.setattr("nexus.database.settings", test_settings)
    reset_db_connection()
    yield
    reset_db_connection()


def test_accept_work_persists(client):
    payload = {"id": "work-1", "type": "echo", "body": {"message": "hello"}}
    response = client.post("/api/work", json=payload)

    assert response.status_code == 202
    work = response.json()
    assert work["id"] == "work-1"
    assert work["status"] == "ACCEPTED"
    assert work["attempt_count"] == 0
    assert work["body"] == {"message": "hello"}

    stored = client.get("/api/work/work-1")
    assert stored.status_code == 200
    assert stored.json()["status"] == "ACCEPTED"


def test_duplicate_accept_returns_existing(client):
    payload = {"id": "work-dup", "type": "echo", "body": {"n": 1}}

    first = client.post("/api/work", json=payload)
    second = client.post("/api/work", json=payload)

    assert first.status_code == 202
    assert second.status_code == 200
    assert first.json()["id"] == second.json()["id"]
    assert first.json()["accepted_at"] == second.json()["accepted_at"]

    listed = client.get("/api/work")
    assert len(listed.json()) == 1


def test_accept_records_event(client):
    client.post("/api/work", json={"id": "work-ev", "type": "echo", "body": {}})

    conn = get_connection()
    rows = conn.execute(
        "SELECT action, reason FROM events WHERE subject_id = ? ORDER BY id",
        ("work-ev",),
    ).fetchall()
    conn.close()

    assert rows[0]["action"] == "accepted"
    assert "persisted" in rows[0]["reason"].lower()


def test_duplicate_accept_records_event(client):
    payload = {"id": "work-dup-ev", "type": "echo", "body": {}}
    client.post("/api/work", json=payload)
    client.post("/api/work", json=payload)

    conn = get_connection()
    rows = conn.execute(
        "SELECT action FROM events WHERE subject_id = ? ORDER BY id",
        ("work-dup-ev",),
    ).fetchall()
    conn.close()

    actions = [row["action"] for row in rows]
    assert actions == ["accepted", "duplicate_accept"]


def test_accepted_work_survives_restart(tmp_path, monkeypatch):
    """Simulate platform restart: new process, same SQLite file."""
    db_path = tmp_path / "restart.db"
    test_settings = Settings(database_path=db_path)
    monkeypatch.setattr("nexus.config.settings", test_settings)
    monkeypatch.setattr("nexus.database.settings", test_settings)

    payload = {"id": "survive-1", "type": "echo", "body": {"keep": True}}

    reset_db_connection()
    app1 = create_app()
    with TestClient(app1) as client1:
        response = client1.post("/api/work", json=payload)
        assert response.status_code == 202

    reset_db_connection()
    app2 = create_app()
    with TestClient(app2) as client2:
        response = client2.get("/api/work/survive-1")
        assert response.status_code == 200
        work = response.json()
        assert work["status"] == "ACCEPTED"
        assert work["body"] == {"keep": True}

    reset_db_connection()
    conn = get_connection(db_path)
    direct = get_work(conn, "survive-1")
    conn.close()
    assert direct is not None
    assert direct.status.value == "ACCEPTED"
