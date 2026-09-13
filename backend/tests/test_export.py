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
        html = client.get(f"/api/scans/{scan['id']}/report/export?format=html")
        assert html.status_code == 200
        assert "<!doctype html>" in html.text
        assert html.headers["content-type"].startswith("text/html")
        docx = client.get(f"/api/scans/{scan['id']}/report/export?format=docx")
        assert docx.status_code == 200
        assert docx.content.startswith(b"PK")
        pdf = client.get(f"/api/scans/{scan['id']}/report/export?format=pdf")
        assert pdf.status_code in {200, 503}
        if pdf.status_code == 200:
            assert pdf.content.startswith(b"%PDF")
        history = client.get(f"/api/projects/{project['id']}/reports")
        assert history.status_code == 200
        assert {item["format"] for item in history.json()} >= {"json", "markdown", "html", "docx", "pdf"}
        assert client.get(f"/api/projects/{project['id']}/scans").status_code == 200
