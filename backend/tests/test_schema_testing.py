import json
import time
import httpx
import pytest

from fastapi.testclient import TestClient

from app.main import app
from app.services.schema_testing import derive_schema_cases, execute_generated_case, validate_json_schema


OPENAPI = {
    "openapi": "3.0.3",
    "security": [{"bearerAuth": []}],
    "paths": {
        "/orders/{order_id}": {
            "get": {
                "operationId": "readOrder",
                "parameters": [
                    {"name": "order_id", "in": "path", "required": True,
                     "schema": {"type": "integer", "minimum": 1, "maximum": 999}},
                    {"name": "state", "in": "query", "schema": {"type": "string", "enum": ["open", "closed"]}},
                ],
                "responses": {"200": {"description": "Order"}, "403": {"description": "Forbidden"}},
            }
        }
    },
}


def test_schema_derivation_produces_contract_logical_and_real_boundaries():
    cases = derive_schema_cases(OPENAPI, "openapi.json")
    assert {case["category"] for case in cases} == {"CONTRACT", "LOGICAL", "EDGE"}
    logical = next(case for case in cases if case["category"] == "LOGICAL")
    assert logical["actor"] == "unauthenticated"
    assert logical["expected"]["status_codes"] == ["401", "403"]
    variants = {case["input_data"].get("value") for case in cases if case["category"] == "EDGE"}
    assert {None, 0, 1000, "__qsscope_invalid_enum__"} <= variants


def test_generated_cases_are_persisted_idempotently_and_filterable(tmp_path):
    (tmp_path / "openapi.json").write_text(json.dumps(OPENAPI))
    with TestClient(app) as client:
        project = client.post("/api/projects/discover", json={"root_path": str(tmp_path)}).json()
        first = client.post(f"/api/projects/{project['id']}/generated-tests/derive")
        assert first.status_code == 200
        assert first.json()["generated"] == 6
        assert first.json()["total"] == 6
        second = client.post(f"/api/projects/{project['id']}/generated-tests/derive").json()
        assert second["generated"] == 0
        assert second["total"] == 6
        edge = client.get(f"/api/projects/{project['id']}/generated-tests", params={"category": "EDGE"})
        assert edge.status_code == 200
        assert len(edge.json()) == 4
        assert all(item["status"] == "GENERATED" for item in edge.json())


def test_derivation_requires_detected_schema(tmp_path):
    with TestClient(app) as client:
        project = client.post("/api/projects/discover", json={"root_path": str(tmp_path)}).json()
        response = client.post(f"/api/projects/{project['id']}/generated-tests/derive")
        assert response.status_code == 409
        assert "No OpenAPI" in response.json()["error"]["message"]


@pytest.mark.asyncio
async def test_generated_cases_execute_against_loopback_with_expected_status():
    async def handler(request: httpx.Request) -> httpx.Response:
        if not request.headers.get("authorization"):
            return httpx.Response(401)
        return httpx.Response(200, json={"id": 1})

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        logical = next(case for case in derive_schema_cases(OPENAPI, "openapi.json") if case["category"] == "LOGICAL")
        result = await execute_generated_case(client, "http://127.0.0.1:8000", logical)
        assert result["status"] == "PASSED"
        contract = next(case for case in derive_schema_cases(OPENAPI, "openapi.json") if case["category"] == "CONTRACT")
        blocked = await execute_generated_case(client, "http://127.0.0.1:8000", contract)
        assert blocked["status"] == "BLOCKED"
        passed = await execute_generated_case(client, "http://127.0.0.1:8000", contract,
                                              {"Authorization": "Bearer local-test"})
        assert passed["status"] == "PASSED"


def test_generated_test_runner_rejects_non_loopback_target(tmp_path):
    (tmp_path / "openapi.json").write_text(json.dumps(OPENAPI))
    with TestClient(app) as client:
        project = client.post("/api/projects/discover", json={"root_path": str(tmp_path)}).json()
        client.post(f"/api/projects/{project['id']}/generated-tests/derive")
        response = client.post(f"/api/projects/{project['id']}/generated-tests/run",
                               json={"base_url": "https://example.com"})
        assert response.status_code == 422
        assert "loopback" in response.json()["error"]["message"]


def test_failed_generated_case_normalizes_to_scan_finding(tmp_path, monkeypatch):
    (tmp_path / "openapi.json").write_text(json.dumps(OPENAPI))

    async def fail_case(*_args, **_kwargs):
        return {"status": "FAILED", "evidence": {"actual_status": 200, "expected_statuses": ["401", "403"]}}

    monkeypatch.setattr("app.api.routes.generated_tests.execute_generated_case", fail_case)
    with TestClient(app) as client:
        project = client.post("/api/projects/discover", json={"root_path": str(tmp_path)}).json()
        client.post(f"/api/projects/{project['id']}/generated-tests/derive")
        scan = client.post(f"/api/projects/{project['id']}/scans", json={"mode": "QUICK"}).json()
        for _ in range(100):
            state = client.get(f"/api/scans/{scan['id']}").json()
            if state["status"] in {"COMPLETED", "FAILED", "ERROR"}:
                break
            time.sleep(0.03)
        run = client.post(f"/api/projects/{project['id']}/generated-tests/run",
                          json={"base_url": "http://127.0.0.1:8000", "scan_id": scan["id"]})
        assert run.status_code == 200
        assert run.json()["failed"] == run.json()["total"]
        findings = client.get(f"/api/scans/{scan['id']}/findings").json()
        generated = [item for item in findings if item["tool"] == "qsscope-schema"]
        assert generated
        assert any(item["category"] == "SECURITY" and item["severity"] == "HIGH" for item in generated)
        report = client.get(f"/api/scans/{scan['id']}/report").json()
        assert report["generated_test_count"] == 6
        assert report["generated_test_failed"] == 6


@pytest.mark.asyncio
async def test_local_refs_request_body_and_response_contract_are_enforced():
    document = {
        "openapi": "3.0.3",
        "components": {"schemas": {
            "CreateOrder": {"type": "object", "required": ["quantity"],
                            "properties": {"quantity": {"type": "integer", "minimum": 1}}},
            "Order": {"type": "object", "required": ["id"],
                      "properties": {"id": {"type": "integer"}}},
        }},
        "paths": {"/orders": {"post": {
            "requestBody": {"required": True, "content": {"application/json": {
                "schema": {"$ref": "#/components/schemas/CreateOrder"}}}},
            "responses": {"201": {"description": "Created", "content": {"application/json": {
                "schema": {"$ref": "#/components/schemas/Order"}}}}},
        }}},
    }
    cases = derive_schema_cases(document, "openapi.json")
    contract = next(case for case in cases if case["category"] == "CONTRACT")
    assert contract["input_data"]["body"] == {"quantity": 1}
    assert any("missing required request body" in case["title"] for case in cases)

    async def invalid_handler(request: httpx.Request) -> httpx.Response:
        assert json.loads(request.content) == {"quantity": 1}
        return httpx.Response(201, json={"name": "missing-id"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(invalid_handler)) as client:
        result = await execute_generated_case(client, "http://127.0.0.1:8000", contract)
    assert result["status"] == "FAILED"
    assert result["evidence"]["schema_errors"] == ["$.id is required"]
    assert validate_json_schema({"id": 1}, contract["expected"]["response_schema"]) == []


@pytest.mark.asyncio
async def test_explicit_role_owner_and_state_rules_derive_and_execute_with_provenance():
    document = {"openapi": "3.0.3", "x-qsscope-roles": ["admin", "viewer"], "paths": {
        "/orders/{order_id}/approve": {"post": {
            "x-qsscope-roles": ["admin"],
            "x-qsscope-ownership": {"parameter": "order_id", "in": "path", "actor": "viewer",
                                      "owner_value": 1, "other_value": 2},
            "x-qsscope-state-transitions": [
                {"from": "PENDING", "to": "APPROVED", "valid": True, "actor": "admin", "status_codes": [200]},
                {"from": "CANCELLED", "to": "APPROVED", "valid": False, "actor": "admin", "status_codes": [409]},
            ],
            "responses": {"200": {"description": "approved"}, "403": {"description": "forbidden"},
                          "409": {"description": "invalid transition"}},
        }}
    }}
    cases = derive_schema_cases(document, "openapi.json")
    families = {case["evidence"].get("rule_family") for case in cases if case["category"] == "LOGICAL"}
    assert {"WRONG_ROLE", "CROSS_OWNER", "STATE_TRANSITION"} <= families
    assert all(case["evidence"].get("provenance") and case["evidence"].get("confidence") == 1.0
               for case in cases if case["evidence"].get("rule_family"))

    async def handler(request: httpx.Request) -> httpx.Response:
        role = request.headers.get("x-role")
        if role == "viewer":
            return httpx.Response(403)
        body = json.loads(request.content) if request.content else {}
        return httpx.Response(409 if body.get("state") == "APPROVED" else 200)

    wrong_role = next(case for case in cases if case["evidence"].get("rule_family") == "WRONG_ROLE")
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await execute_generated_case(client, "http://127.0.0.1:8000", wrong_role,
                                              actor_profiles={"viewer": {"X-Role": "viewer"}})
    assert result["status"] == "PASSED"
    assert result["evidence"]["actor"] == "viewer"
