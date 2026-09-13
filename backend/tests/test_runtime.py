"""Scan runtime service tests."""
import asyncio

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.runtime import _command_for_task


def test_runtime_whitelists_known_commands(tmp_path):
    assert _command_for_task({"task_id": "python-compile", "tool": "python"}, tmp_path) == [
        "python", "-m", "compileall", "-q", "."
    ]
    assert _command_for_task({"task_id": "arbitrary", "tool": "sh"}, tmp_path) is None


@pytest.mark.asyncio
async def test_runtime_command_is_not_shell_parsed(tmp_path):
    command = _command_for_task({"task_id": "python-tests", "tool": "pytest"}, tmp_path)
    assert command == ["pytest", "-q"]
    assert all(";" not in part and "|" not in part for part in command)


def test_scan_endpoint_creates_session(tmp_path):
    with TestClient(app) as client:
        discovered = client.post("/api/projects/discover", json={"root_path": str(tmp_path)})
        assert discovered.status_code == 200
        project_id = discovered.json()["id"]
        started = client.post(f"/api/projects/{project_id}/scans", json={"mode": "QUICK"})
        assert started.status_code == 202
        assert started.json()["status"] in {"PENDING", "RUNNING", "COMPLETED"}
