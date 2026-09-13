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
