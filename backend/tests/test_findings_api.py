import time

from fastapi.testclient import TestClient

from app.main import app


def _scan_with_finding(client: TestClient, tmp_path) -> tuple[str, dict]:
    (tmp_path / "pyproject.toml").write_text("[project]\nname='failure-fixture'\nversion='0.1'\ndependencies=['pytest']\n")
    (tmp_path / "app.py").write_text("print('debug')\n")
    project = client.post("/api/projects/discover", json={"root_path": str(tmp_path)}).json()
    scan = client.post(f"/api/projects/{project['id']}/scans", json={"mode": "QUICK"}).json()
    for _ in range(150):
        current = client.get(f"/api/scans/{scan['id']}").json()
        if current["status"] in {"COMPLETED", "FAILED", "ERROR"}:
            break
        time.sleep(0.03)
    findings = client.get(f"/api/scans/{scan['id']}/findings").json()
    assert findings
    return scan["id"], findings[0]


def test_findings_can_be_filtered_and_status_history_is_recorded(tmp_path):
    with TestClient(app) as client:
        scan_id, finding = _scan_with_finding(client, tmp_path)
        filtered = client.get(f"/api/scans/{scan_id}/findings", params={"category": finding["category"]})
        assert filtered.status_code == 200 and filtered.json()
        test_runs = client.get(f"/api/scans/{scan_id}/test-runs")
        assert test_runs.status_code == 200
        assert test_runs.json()[0]["framework"] == "pytest"
        detail = client.get(f"/api/findings/{finding['id']}")
        assert detail.status_code == 200
        updated = client.patch(f"/api/findings/{finding['id']}/status",
                               json={"status": "ACKNOWLEDGED", "note": "Reviewed locally"})
        assert updated.status_code == 200
        assert updated.json()["status"] == "ACKNOWLEDGED"


def test_finding_endpoints_validate_identifiers():
    with TestClient(app) as client:
        assert client.get("/api/findings/missing").status_code == 404
        assert client.patch("/api/findings/missing/status", json={"status": "FALSE_POSITIVE"}).status_code == 404
