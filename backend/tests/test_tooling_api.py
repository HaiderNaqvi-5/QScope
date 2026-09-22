from fastapi.testclient import TestClient

from app.main import app


def test_global_tooling_status_exposes_metadata():
    with TestClient(app) as client:
        response = client.get("/api/tooling/status")
    assert response.status_code == 200
    tools = response.json()
    semgrep = next(item for item in tools if item["id"] == "semgrep")
    assert semgrep["categories"] == ["sast"]
    assert semgrep["adapter"] == "universal"
    assert semgrep["license"]
    assert semgrep["status"] in {"READY", "OPTIONAL_NOT_INSTALLED", "ERROR"}


def test_project_tooling_status_rejects_unknown_project():
    with TestClient(app) as client:
        response = client.post("/api/tooling/recheck?project_id=missing")
    assert response.status_code == 404
