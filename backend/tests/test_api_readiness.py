"""OpenAPI discovery and API readiness tests."""
import json

from fastapi.testclient import TestClient

from app.main import app


def test_openapi_spec_is_detected_and_full_plan_contains_runtime_stage(tmp_path):
    (tmp_path / "openapi.json").write_text(json.dumps({"openapi": "3.0.0", "paths": {}}))
    with TestClient(app) as client:
        project = client.post("/api/projects/discover", json={"root_path": str(tmp_path)}).json()
        assert project["model"]["api_specs"][0]["value"] == "OpenAPI"
        plan = client.get(f"/api/projects/{project['id']}/scan-plan?mode=FULL").json()
        runtime_task = next(task for task in plan["tasks"] if task["task_id"] == "runtime-api")
        assert runtime_task["requires_user_confirmation"] is True
        assert runtime_task["target"] == "unconfigured"


def test_runtime_target_is_loopback_only_and_updates_plan(tmp_path):
    (tmp_path / "openapi.json").write_text(json.dumps({"openapi": "3.0.0", "paths": {}}))
    with TestClient(app) as client:
        project = client.post("/api/projects/discover", json={"root_path": str(tmp_path)}).json()
        rejected = client.post(
            f"/api/projects/{project['id']}/runtime-target",
            json={"host": "0.0.0.0", "port": 8000},
        )
        assert rejected.status_code == 422
        configured = client.post(
            f"/api/projects/{project['id']}/runtime-target",
            json={"host": "127.0.0.1", "port": 8000},
        )
        assert configured.status_code == 200
        plan = client.get(f"/api/projects/{project['id']}/scan-plan?mode=FULL").json()
        runtime_task = next(task for task in plan["tasks"] if task["task_id"] == "runtime-api")
        assert runtime_task["target"] == "http://127.0.0.1:8000"


def test_postman_collection_is_detected_and_planned(tmp_path):
    (tmp_path / "local.postman_collection.json").write_text(json.dumps({"info": {"name": "local"}, "item": []}))
    with TestClient(app) as client:
        project = client.post("/api/projects/discover", json={"root_path": str(tmp_path)}).json()
        assert project["model"]["postman_collections"][0]["value"] == "Postman collection"
        plan = client.get(f"/api/projects/{project['id']}/scan-plan?mode=FULL").json()
        task = next(task for task in plan["tasks"] if task["task_id"] == "runtime-postman")
        assert task["requires_user_confirmation"] is True
        assert task["target"] == "unconfigured"


def test_playwright_project_is_detected_and_planned(tmp_path):
    (tmp_path / "playwright.config.ts").write_text("export default {};")
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "home.spec.ts").write_text("import { test } from '@playwright/test';")
    with TestClient(app) as client:
        project = client.post("/api/projects/discover", json={"root_path": str(tmp_path)}).json()
        assert project["model"]["browser_tests"]
        plan = client.get(f"/api/projects/{project['id']}/scan-plan?mode=FULL").json()
        task = next(task for task in plan["tasks"] if task["task_id"] == "browser-functional")
        assert task["requires_user_confirmation"] is True
        assert task["target"] == "unconfigured"


def test_accessibility_and_performance_capabilities_are_planned(tmp_path):
    (tmp_path / "package.json").write_text(json.dumps({
        "devDependencies": {"@playwright/test": "^1.40.0", "@axe-core/playwright": "^4.0.0", "lighthouse": "^12.0.0"},
    }))
    with TestClient(app) as client:
        project = client.post("/api/projects/discover", json={"root_path": str(tmp_path)}).json()
        assert project["model"]["accessibility_tests"]
        assert project["model"]["performance_tests"]
        plan = client.get(f"/api/projects/{project['id']}/scan-plan?mode=FULL").json()
        assert next(task for task in plan["tasks"] if task["task_id"] == "browser-accessibility")["requires_user_confirmation"]
        assert next(task for task in plan["tasks"] if task["task_id"] == "browser-performance")["requires_user_confirmation"]


def test_graphql_schema_is_detected_and_planned(tmp_path):
    (tmp_path / "schema.graphql").write_text("type Query { health: String }")
    with TestClient(app) as client:
        project = client.post("/api/projects/discover", json={"root_path": str(tmp_path)}).json()
        assert project["model"]["graphql_specs"][0]["value"] == "GraphQL"
        plan = client.get(f"/api/projects/{project['id']}/scan-plan?mode=FULL").json()
        task = next(task for task in plan["tasks"] if task["task_id"] == "runtime-graphql")
        assert task["requires_user_confirmation"] is True


def test_runtime_health_reports_unreachable_loopback_target(tmp_path):
    with TestClient(app) as client:
        project = client.post("/api/projects/discover", json={"root_path": str(tmp_path)}).json()
        client.post(
            f"/api/projects/{project['id']}/runtime-target",
            json={"host": "127.0.0.1", "port": 1, "scheme": "http"},
        )
        health = client.get(f"/api/projects/{project['id']}/runtime-target/health")
        assert health.status_code == 200
        assert health.json()["status"] == "UNREACHABLE"
