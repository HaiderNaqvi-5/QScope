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
        expected_formats = {"json", "markdown", "html", "docx"}
        if pdf.status_code == 200:
            expected_formats.add("pdf")
        assert {item["format"] for item in history.json()} >= expected_formats
        assert client.get(f"/api/projects/{project['id']}/scans").status_code == 200


def test_pdf_export_history_matches_renderer_result(tmp_path):
    with TestClient(app) as client:
        project = client.post("/api/projects/discover", json={"root_path": str(tmp_path)}).json()
        scan = client.post(f"/api/projects/{project['id']}/scans", json={"mode": "QUICK"}).json()
        for _ in range(20):
            if client.get(f"/api/scans/{scan['id']}/report").status_code == 200:
                break
            time.sleep(0.05)
        response = client.get(f"/api/scans/{scan['id']}/report/export?format=pdf")
        history = client.get(f"/api/projects/{project['id']}/reports").json()
        has_pdf = any(item["format"] == "pdf" for item in history)
        assert has_pdf is (response.status_code == 200)
