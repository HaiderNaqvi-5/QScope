"""Report export and scan history tests."""
import time

from fastapi.testclient import TestClient

from app.main import app


def test_report_exports_json_and_markdown(tmp_path):
    with TestClient(app) as client:
        project = client.post("/api/projects/discover", json={"root_path": str(tmp_path)}).json()
        scan = client.post(f"/api/projects/{project['id']}/scans", json={"mode": "QUICK"}).json()
        for _ in range(20):
            report = client.get(f"/api/scans/{scan['id']}/report")
            if report.status_code == 200 and report.json()["status"] == "COMPLETED":
                break
            time.sleep(0.05)
        assert client.get(f"/api/scans/{scan['id']}/report/export?format=json").headers["content-type"].startswith("application/json")
        markdown = client.get(f"/api/scans/{scan['id']}/report/export?format=markdown")
        assert markdown.status_code == 200
        assert "# QSScope Scan Report" in markdown.text
        assert client.get(f"/api/projects/{project['id']}/scans").status_code == 200
