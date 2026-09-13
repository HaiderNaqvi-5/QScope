"""Durable scan lifecycle transition tests."""
import json

from fastapi.testclient import TestClient

from app.main import app


def test_awaiting_scan_can_be_cancelled_without_starting(tmp_path):
    (tmp_path / "openapi.json").write_text(json.dumps({"openapi": "3.0.0", "paths": {}}))
    with TestClient(app) as client:
        project = client.post("/api/projects/discover", json={"root_path": str(tmp_path)}).json()
        scan = client.post(f"/api/projects/{project['id']}/scans", json={"mode": "FULL"}).json()
        cancelled = client.post(f"/api/scans/{scan['id']}/cancel")
        assert cancelled.status_code == 200
        assert cancelled.json()["status"] == "CANCELLED"
        assert client.post(f"/api/scans/{scan['id']}/approve").status_code == 409
