"""Baseline regression API tests."""
import time

from fastapi.testclient import TestClient

from app.main import app


def test_report_can_create_baseline(tmp_path):
    with TestClient(app) as client:
        project = client.post("/api/projects/discover", json={"root_path": str(tmp_path)}).json()
        scan = client.post(f"/api/projects/{project['id']}/scans", json={"mode": "QUICK"}).json()
        for _ in range(20):
            report = client.get(f"/api/scans/{scan['id']}/report")
            if report.status_code == 200 and report.json()["status"] == "COMPLETED":
                break
            time.sleep(0.05)
        baseline = client.post(f"/api/scans/{scan['id']}/baseline")
        assert baseline.status_code == 200
        assert baseline.json()["existing_findings"] == 0
        assert baseline.json()["resolved_findings"] == 0
