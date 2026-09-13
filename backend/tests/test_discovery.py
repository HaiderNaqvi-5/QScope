"""Acceptance coverage for deterministic project discovery."""
import json

from fastapi.testclient import TestClient

from app.main import app


def test_discover_react_fastapi_project(tmp_path):
    (tmp_path / "package.json").write_text(json.dumps({
        "dependencies": {"react": "^18", "next": "^14"},
        "scripts": {"dev": "next dev", "build": "next build"},
    }))
    (tmp_path / "pyproject.toml").write_text("[project]\nname='demo'\ndependencies=['fastapi', 'pytest']\n")
    (tmp_path / "main.py").write_text("from fastapi import FastAPI\n")
    with TestClient(app) as client:
        response = client.post("/api/projects/discover", json={"root_path": str(tmp_path)})
    assert response.status_code == 200
    data = response.json()
    values = {item["value"] for item in data["model"]["languages"]}
    frameworks = {item["value"] for item in data["model"]["frameworks"]}
    assert {"Python", "JavaScript"} <= values
    assert {"React", "Next.js"} <= frameworks
    assert "npm run build" in data["model"]["build_commands"]


def test_scan_plan_contains_preflight(tmp_path):
    with TestClient(app) as client:
        response = client.post("/api/projects/discover", json={"root_path": str(tmp_path)})
        assert response.status_code == 200
        project_id = response.json()["id"]
        plan = client.get(f"/api/projects/{project_id}/scan-plan")
    assert plan.status_code == 200
    assert any(task["stage"] == "PREFLIGHT" for task in plan.json()["tasks"])
