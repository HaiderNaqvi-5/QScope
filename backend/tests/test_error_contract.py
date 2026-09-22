from fastapi.testclient import TestClient

from app.main import app


def test_http_errors_use_v13_envelope():
    with TestClient(app) as client:
        response = client.get("/api/scans/does-not-exist")
    assert response.status_code == 404
    assert response.json() == {"error": {"code": "NOT_FOUND", "message": "Scan session not found",
        "details": {}, "recoverable": True, "suggested_action": None}}


def test_validation_errors_do_not_expose_framework_tracebacks():
    with TestClient(app) as client:
        response = client.post("/api/projects/discover", json={"root_path": 7})
    body = response.json()
    assert response.status_code == 422
    assert body["error"]["code"] == "VALIDATION_ERROR"
    assert body["error"]["details"]
    assert "traceback" not in response.text.lower()
