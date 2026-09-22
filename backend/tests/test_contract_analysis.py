import json

from app.services.contract_analysis import analyze_contracts
from app.services.findings import normalize_tool_output


def test_frontend_stale_response_field_has_both_source_evidence(tmp_path):
    (tmp_path / "openapi.json").write_text(json.dumps({"openapi": "3.0.3", "paths": {
        "/api/users/{user_id}": {"get": {"responses": {"200": {"description": "user", "content": {
            "application/json": {"schema": {"type": "object", "properties": {
                "id": {"type": "integer"}, "name": {"type": "string"}}}}}}}}}
    }}))
    (tmp_path / "page.tsx").write_text("""async function load() {
      const response = await fetch('/api/users/1');
      const data = await response.json();
      return data.staleDisplayName;
    }""")
    issues = analyze_contracts(tmp_path)
    stale = next(item for item in issues if item["kind"] == "RESPONSE_FIELD_MISMATCH")
    assert stale["frontend_file"] == "page.tsx"
    assert stale["api_spec"] == "openapi.json"
    assert stale["field"] == "staleDisplayName"
    findings = normalize_tool_output("scan", {"tool": "qsscope-contract", "stage": "CONTRACT_TESTING",
                                                  "status": "FAILED", "output": json.dumps({"issues": issues})})
    assert findings[0]["evidence"]["declared_fields"] == ["id", "name"]


def test_contract_analysis_detects_route_and_method_mismatch(tmp_path):
    (tmp_path / "openapi.json").write_text(json.dumps({"openapi": "3.0.3", "paths": {
        "/api/orders": {"get": {"responses": {"200": {"description": "ok"}}}}
    }}))
    (tmp_path / "api.ts").write_text("fetch('/api/orders', {method: 'DELETE'}); fetch('/api/missing');")
    kinds = {item["kind"] for item in analyze_contracts(tmp_path)}
    assert kinds == {"METHOD_MISMATCH", "ROUTE_MISMATCH"}


def test_contract_analysis_detects_request_shape_drift(tmp_path):
    (tmp_path / "openapi.json").write_text(json.dumps({"openapi": "3.0.3", "paths": {
        "/api/orders": {"post": {"requestBody": {"content": {"application/json": {"schema": {
            "type": "object", "required": ["quantity"], "properties": {"quantity": {"type": "integer"}}
        }}}}, "responses": {"201": {"description": "ok"}}}}
    }}))
    (tmp_path / "api.ts").write_text("fetch('/api/orders', {method:'POST', body: JSON.stringify({qty: 2})});")
    issues = analyze_contracts(tmp_path)
    assert {item["kind"] for item in issues} == {"REQUEST_FIELD_MISMATCH", "MISSING_REQUIRED_REQUEST_FIELDS"}
