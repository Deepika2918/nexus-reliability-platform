"""Verify read-only operator dashboard APIs."""


def test_operator_summary_empty(client):
    res = client.get("/api/operator/summary")
    assert res.status_code == 200
    data = res.json()
    assert data["total_work"] == 0
    assert data["registered_workers"] == 0
    assert data["health"] == "ok"


def test_operator_work_list(client):
    client.post("/api/work", json={"id": "dash-1", "type": "echo", "body": {"priority": "high"}})

    res = client.get("/api/operator/work")
    assert res.status_code == 200
    items = res.json()
    assert len(items) == 1
    assert items[0]["id"] == "dash-1"
    assert items[0]["status"] == "ACCEPTED"
    assert items[0]["priority"] == "high"
    assert items[0]["attempt_count"] == 0
    assert items[0]["failure_reason"] is None


def test_operator_workers_list(client):
    client.post("/api/workers/register", json={"id": "worker-dash"})

    res = client.get("/api/operator/workers")
    assert res.status_code == 200
    workers = res.json()
    assert len(workers) == 1
    assert workers[0]["id"] == "worker-dash"
    assert workers[0]["status"] == "RUNNING"
    assert workers[0]["current_work_id"] is None


def test_operator_workers_show_current_work(client):
    client.post("/api/workers/register", json={"id": "worker-dash"})
    client.post("/api/work", json={"id": "dash-job", "type": "echo", "body": {}})
    client.post("/api/workers/worker-dash/poll")

    res = client.get("/api/operator/workers")
    worker = res.json()[0]
    assert worker["current_work_id"] == "dash-job"
    assert worker["lease_expires_at"] is not None


def test_operator_summary_counts(client):
    client.post("/api/workers/register", json={"id": "w1"})
    client.post("/api/work", json={"id": "j1", "type": "echo", "body": {}})
    client.post("/api/work", json={"id": "j2", "type": "echo", "body": {}})
    client.post("/api/workers/w1/poll")

    res = client.get("/api/operator/summary")
    data = res.json()
    assert data["total_work"] == 2
    assert data["accepted"] == 1
    assert data["processing"] == 1
    assert data["registered_workers"] == 1


def test_operator_events(client):
    client.post("/api/work", json={"id": "ev-work", "type": "echo", "body": {}})

    res = client.get("/api/operator/events?limit=10")
    assert res.status_code == 200
    events = res.json()
    assert len(events) >= 1
    assert events[0]["action"] == "accepted"
    assert events[0]["work_id"] == "ev-work"


def test_operator_snapshot(client):
    client.post("/api/workers/register", json={"id": "w1"})
    client.post("/api/work", json={"id": "snap-1", "type": "echo", "body": {"priority": "low"}})

    res = client.get("/api/operator/snapshot")
    assert res.status_code == 200
    data = res.json()
    assert "summary" in data
    assert "work" in data
    assert "workers" in data
    assert "events" in data
    assert data["summary"]["total_work"] == 1
    assert data["work"][0]["priority"] == "low"


def test_dashboard_page_loads(client):
    res = client.get("/")
    assert res.status_code == 200
    assert "NEXUS Operator Dashboard" in res.text


def test_operator_endpoints_are_read_only(client):
    assert client.post("/api/operator/summary").status_code == 405
    assert client.post("/api/operator/work").status_code == 405
    assert client.post("/api/operator/workers").status_code == 405
    assert client.post("/api/operator/events").status_code == 405
