import time

from fastapi.testclient import TestClient

from app.main import app


def test_scan_tasks_and_events_are_persisted_for_recovery(tmp_path):
    with TestClient(app) as client:
        project = client.post("/api/projects/discover", json={"root_path": str(tmp_path)}).json()
        scan = client.post(f"/api/projects/{project['id']}/scans", json={"mode": "QUICK"}).json()
        for _ in range(100):
            current = client.get(f"/api/scans/{scan['id']}").json()
            if current["status"] in {"COMPLETED", "FAILED", "ERROR"}:
                break
            time.sleep(0.03)
        tasks = client.get(f"/api/scans/{scan['id']}/tasks")
        events = client.get(f"/api/scans/{scan['id']}/event-history")
        completed_scan = client.get(f"/api/scans/{scan['id']}").json()
    assert tasks.status_code == 200
    assert len(tasks.json()) >= 4
    assert all(task["status"] != "PENDING" for task in tasks.json())
    assert events.status_code == 200
    names = {event["event"] for event in events.json()}
    assert "scan.started" in names
    assert "scan.completed" in names or "scan.failed" in names
    assert all(event["payload"] for event in events.json())
    assert len(completed_scan["project_fingerprint"]) == 64
    assert completed_scan["overall_score"] is not None
    assert completed_scan["release_readiness"] in {
        "RELEASE READY", "READY WITH WARNINGS", "NOT READY", "INCOMPLETE AUDIT"
    }


def test_unknown_scan_task_history_is_404():
    with TestClient(app) as client:
        assert client.get("/api/scans/missing/tasks").status_code == 404
        assert client.get("/api/scans/missing/event-history").status_code == 404
