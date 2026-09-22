"""Acceptance coverage for safe per-project runtime management."""
import socket
import sys

from fastapi.testclient import TestClient

from app.main import app
from app.services.runtime_manager import validate_local_url


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def test_runtime_urls_are_loopback_only():
    assert validate_local_url("http://127.0.0.1:8123") == "http://127.0.0.1:8123"
    assert validate_local_url("http://localhost:8123/health") == "http://localhost:8123/health"
    try:
        validate_local_url("https://example.com")
    except ValueError as exc:
        assert "loopback" in str(exc)
    else:
        raise AssertionError("public runtime target was accepted")


def test_runtime_profile_requires_approval_and_stops_cleanly(tmp_path):
    port = _free_port()
    with TestClient(app) as client:
        project = client.post("/api/projects/discover", json={"root_path": str(tmp_path)}).json()
        created = client.post(f"/api/projects/{project['id']}/runtime-profiles", json={
            "name": "fixture", "working_directory": ".",
            "command": [sys.executable, "-m", "http.server", str(port), "--bind", "127.0.0.1"],
            "local_url": f"http://127.0.0.1:{port}", "startup_timeout_seconds": 5,
        })
        assert created.status_code == 201
        profile_id = created.json()["id"]
        assert client.post(f"/api/runtime-profiles/{profile_id}/start", json={}).status_code == 409
        started = client.post(f"/api/runtime-profiles/{profile_id}/start", json={"approved": True})
        assert started.status_code == 200
        assert started.json()["status"] == "READY"
        stopped = client.post(f"/api/runtime-profiles/{profile_id}/stop")
        assert stopped.status_code == 200
        assert stopped.json()["status"] == "STOPPED"


def test_runtime_profile_rejects_workspace_escape(tmp_path):
    with TestClient(app) as client:
        project = client.post("/api/projects/discover", json={"root_path": str(tmp_path)}).json()
        response = client.post(f"/api/projects/{project['id']}/runtime-profiles", json={
            "name": "escape", "working_directory": "../", "command": ["python", "-V"],
            "local_url": "http://127.0.0.1:8000",
        })
        assert response.status_code == 422
