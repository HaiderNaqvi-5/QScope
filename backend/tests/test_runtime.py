"""Scan runtime service tests."""
import asyncio
import time

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services import runtime
from app.services.runtime import _command_for_task


def test_runtime_whitelists_known_commands(tmp_path):
    assert _command_for_task({"task_id": "python-compile", "tool": "python"}, tmp_path) == [
        "python", "-m", "compileall", "-q", "."
    ]
    assert _command_for_task({"task_id": "arbitrary", "tool": "sh"}, tmp_path) is None
    api_command = _command_for_task(
        {"task_id": "runtime-api", "tool": "schemathesis", "target": "http://127.0.0.1:8000"},
        tmp_path,
    )
    if api_command is not None:
        assert api_command[-2:] == ["--base-url", "http://127.0.0.1:8000"]


@pytest.mark.asyncio
async def test_runtime_command_is_not_shell_parsed(tmp_path):
    command = _command_for_task({"task_id": "python-tests", "tool": "pytest"}, tmp_path)
    assert command == ["pytest", "-q"]
    assert all(";" not in part and "|" not in part for part in command)


def test_optional_security_and_load_commands_are_fixed_vectors(tmp_path, monkeypatch):
    (tmp_path / "smoke.k6.js").write_text("export default function () {}")
    (tmp_path / "plan.jmx").write_text("<jmeterTestPlan/>")
    monkeypatch.setattr(runtime.shutil, "which", lambda executable: executable)
    zap = _command_for_task(
        {"task_id": "runtime-zap", "tool": "zap-baseline.py", "target": "http://127.0.0.1:8000"},
        tmp_path,
    )
    k6 = _command_for_task(
        {"task_id": "runtime-k6", "tool": "k6", "target": "http://127.0.0.1:8000"},
        tmp_path,
    )
    jmeter = _command_for_task(
        {"task_id": "runtime-jmeter", "tool": "jmeter", "target": "http://127.0.0.1:8000"},
        tmp_path,
    )
    assert zap == ["zap-baseline.py", "-t", "http://127.0.0.1:8000", "-J", "-"]
    assert k6 == ["k6", "run", "--vus", "1", "--duration", "10s", str(tmp_path / "smoke.k6.js")]
    assert jmeter[:5] == ["jmeter", "-n", "-t", str(tmp_path / "plan.jmx"), "-JbaseUrl=http://127.0.0.1:8000"]
    assert all(";" not in part and "|" not in part for part in (zap + k6 + jmeter))


def test_scan_endpoint_creates_session(tmp_path):
    with TestClient(app) as client:
        discovered = client.post("/api/projects/discover", json={"root_path": str(tmp_path)})
        assert discovered.status_code == 200
        project_id = discovered.json()["id"]
        started = client.post(f"/api/projects/{project_id}/scans", json={"mode": "QUICK"})
        assert started.status_code == 202
        assert started.json()["status"] in {"PENDING", "RUNNING", "COMPLETED"}


def test_scan_report_is_available_after_completion(tmp_path):
    with TestClient(app) as client:
        discovered = client.post("/api/projects/discover", json={"root_path": str(tmp_path)})
        scan = client.post(f"/api/projects/{discovered.json()['id']}/scans", json={"mode": "QUICK"}).json()
        report = None
        for _ in range(20):
            report = client.get(f"/api/scans/{scan['id']}/report")
            if report.status_code == 200 and report.json()["status"] in {"COMPLETED", "FAILED"}:
                break
            time.sleep(0.05)
        assert report is not None
        assert report.status_code == 200
        assert 0 <= report.json()["score"] <= 100
