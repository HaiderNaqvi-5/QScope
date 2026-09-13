"""Runtime approval gate tests."""
import json

from fastapi.testclient import TestClient

from app.main import app


def test_full_scan_requires_approval_for_api_runtime(tmp_path):
    (tmp_path / "openapi.json").write_text(json.dumps({"openapi": "3.0.0", "paths": {}}))
    with TestClient(app) as client:
        project = client.post("/api/projects/discover", json={"root_path": str(tmp_path)}).json()
        scan = client.post(f"/api/projects/{project['id']}/scans", json={"mode": "FULL"}).json()
        assert scan["status"] == "AWAITING_APPROVAL"
        assert scan["approval_required"] is True
        approved = client.post(f"/api/scans/{scan['id']}/approve")
        assert approved.status_code == 202


def test_full_scan_report_requires_target_before_api_testing(tmp_path):
    (tmp_path / "openapi.json").write_text(json.dumps({"openapi": "3.0.0", "paths": {}}))
    with TestClient(app) as client:
        project = client.post("/api/projects/discover", json={"root_path": str(tmp_path)}).json()
        scan = client.post(f"/api/projects/{project['id']}/scans", json={"mode": "FULL"}).json()
        report = client.get(f"/api/scans/{scan['id']}/report").json()
        assert report["api_testing_status"] == "API_SOURCE_FOUND_TARGET_REQUIRED"
