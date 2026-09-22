import time

from fastapi.testclient import TestClient

from app.main import app
from app.services.artifacts import redact_artifact_text


def test_artifact_redaction_removes_credentials():
    safe = redact_artifact_text("password=hunter2 API_KEY: gsk_abcdefghijklmnop")
    assert "hunter2" not in safe
    assert "gsk_abcdefghijklmnop" not in safe


def test_scan_outputs_are_persisted_and_downloadable(tmp_path):
    with TestClient(app) as client:
        project = client.post("/api/projects/discover", json={"root_path": str(tmp_path)}).json()
        scan = client.post(f"/api/projects/{project['id']}/scans", json={"mode": "QUICK"}).json()
        for _ in range(100):
            current = client.get(f"/api/scans/{scan['id']}").json()
            if current["status"] in {"COMPLETED", "FAILED", "ERROR"}:
                break
            time.sleep(0.03)
        artifacts = client.get(f"/api/scans/{scan['id']}/artifacts")
        assert artifacts.status_code == 200
        assert artifacts.json()
        artifact = artifacts.json()[0]
        assert len(artifact["sha256"]) == 64
        download = client.get(f"/api/artifacts/{artifact['id']}/download")
        assert download.status_code == 200
        assert download.headers["content-type"].startswith(("text/plain", "application/json"))


def test_unknown_artifact_is_not_disclosed():
    with TestClient(app) as client:
        assert client.get("/api/artifacts/missing/download").status_code == 404
