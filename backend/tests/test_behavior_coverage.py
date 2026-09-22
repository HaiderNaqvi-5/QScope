import json
import time

from fastapi.testclient import TestClient

from app.main import app


def test_behavior_coverage_maps_generated_manual_and_suite_evidence(tmp_path):
    specification = {"openapi": "3.0.3", "security": [{"bearer": []}], "paths": {
        "/orders": {"post": {"responses": {"201": {"description": "created"}}}}
    }}
    (tmp_path / "openapi.json").write_text(json.dumps(specification))
    (tmp_path / "pyproject.toml").write_text("[project]\nname='coverage-fixture'\nversion='1'\n")
    with TestClient(app) as client:
        project = client.post("/api/projects/discover", json={"root_path": str(tmp_path)}).json()
        client.post(f"/api/projects/{project['id']}/generated-tests/derive")
        manual = client.post("/api/manual-tests", json={"project_id": project["id"], "module": "Checkout",
            "feature": "Submit", "steps": ["Submit order"], "expected_result": "Order created"}).json()
        client.patch(f"/api/manual-tests/{manual['id']}", json={"status": "PASS", "actual_result": "Created"})
        scan = client.post(f"/api/projects/{project['id']}/scans", json={"mode": "QUICK"}).json()
        for _ in range(100):
            state = client.get(f"/api/scans/{scan['id']}").json()
            if state["status"] in {"COMPLETED", "FAILED", "ERROR"}:
                break
            time.sleep(0.03)
        response = client.post(f"/api/projects/{project['id']}/behavior-coverage/derive",
                               params={"scan_id": scan["id"]})
        assert response.status_code == 200
        summary = response.json()
        assert summary["covered"] >= 1
        assert summary["untested"] >= 2
        logical = next(item for item in summary["records"] if item["category"] == "LOGICAL")
        assert logical["criticality"] == "HIGH"
        assert logical["coverage_status"] == "UNTESTED"
        findings = client.get(f"/api/scans/{scan['id']}/findings").json()
        assert any(item["subcategory"] == "BEHAVIOR_GAP" for item in findings)
        listing = client.get(f"/api/projects/{project['id']}/behavior-coverage")
        assert listing.status_code == 200
        assert len(listing.json()) == summary["total"]
        report = client.get(f"/api/scans/{scan['id']}/report")
        assert report.status_code == 200
        assert report.json()["behavior_coverage_total"] == summary["total"]
        assert report.json()["behavior_coverage_untested"] == summary["untested"]
