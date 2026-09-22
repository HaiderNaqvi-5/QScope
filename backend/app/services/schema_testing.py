"""Deterministic OpenAPI contract, authorization, and boundary-case derivation."""
from __future__ import annotations

import hashlib
import json
import re
import time
from copy import deepcopy
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx


def load_openapi(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8", errors="strict")
    if path.suffix.lower() == ".json":
        payload = json.loads(text)
    else:
        try:
            import yaml
        except ImportError as exc:
            raise ValueError("YAML OpenAPI parsing requires PyYAML") from exc
        payload = yaml.safe_load(text)
    if not isinstance(payload, dict) or not isinstance(payload.get("paths"), dict):
        raise ValueError("OpenAPI document has no paths object")
    return payload


def _fingerprint(source: str, category: str, method: str, endpoint: str, variant: str) -> str:
    return hashlib.sha256("|".join((source, category, method, endpoint, variant)).encode()).hexdigest()


def resolve_local_refs(value: Any, document: dict[str, Any], depth: int = 0) -> Any:
    """Resolve bounded local JSON pointers; remote references are intentionally not fetched."""
    if depth > 20:
        raise ValueError("OpenAPI reference depth exceeds the safety limit")
    if isinstance(value, list):
        return [resolve_local_refs(item, document, depth + 1) for item in value]
    if not isinstance(value, dict):
        return value
    reference = value.get("$ref")
    if reference:
        if not isinstance(reference, str) or not reference.startswith("#/" ):
            raise ValueError("Only local OpenAPI references are supported")
        target: Any = document
        for part in reference[2:].split("/"):
            key = part.replace("~1", "/").replace("~0", "~")
            if not isinstance(target, dict) or key not in target:
                raise ValueError(f"Unresolved OpenAPI reference: {reference}")
            target = target[key]
        merged = deepcopy(target)
        merged.update({key: item for key, item in value.items() if key != "$ref"})
        return resolve_local_refs(merged, document, depth + 1)
    return {key: resolve_local_refs(item, document, depth + 1) for key, item in value.items()}


def sample_from_schema(schema: dict[str, Any]) -> Any:
    if "example" in schema:
        return schema["example"]
    if "default" in schema:
        return schema["default"]
    if schema.get("enum"):
        return schema["enum"][0]
    kind = schema.get("type")
    if kind == "object" or "properties" in schema:
        required = set(schema.get("required", []))
        return {name: sample_from_schema(child) for name, child in schema.get("properties", {}).items()
                if name in required or "default" in child or "example" in child}
    if kind == "array":
        return [sample_from_schema(schema.get("items", {}))]
    if kind == "integer":
        return int(schema.get("minimum", 1))
    if kind == "number":
        return float(schema.get("minimum", 1))
    if kind == "boolean":
        return True
    return "example"


def validate_json_schema(value: Any, schema: dict[str, Any], path: str = "$") -> list[str]:
    """Validate the deterministic contract subset without pretending to be full JSON Schema."""
    errors: list[str] = []
    kind = schema.get("type")
    matches = {"object": isinstance(value, dict), "array": isinstance(value, list),
               "string": isinstance(value, str), "integer": isinstance(value, int) and not isinstance(value, bool),
               "number": isinstance(value, (int, float)) and not isinstance(value, bool),
               "boolean": isinstance(value, bool), "null": value is None}
    if kind in matches and not matches[kind]:
        return [f"{path} expected {kind}"]
    if isinstance(value, dict):
        for name in schema.get("required", []):
            if name not in value:
                errors.append(f"{path}.{name} is required")
        for name, child in schema.get("properties", {}).items():
            if name in value:
                errors.extend(validate_json_schema(value[name], child, f"{path}.{name}"))
    if isinstance(value, list) and isinstance(schema.get("items"), dict):
        for index, item in enumerate(value[:1000]):
            errors.extend(validate_json_schema(item, schema["items"], f"{path}[{index}]"))
    return errors


def derive_schema_cases(document: dict[str, Any], source_path: str) -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    declared_roles = [str(role) for role in document.get("x-qsscope-roles", []) if str(role).strip()]
    for endpoint, path_item in sorted(document.get("paths", {}).items()):
        if not isinstance(path_item, dict):
            continue
        shared_parameters = path_item.get("parameters", [])
        for method, operation in sorted(path_item.items()):
            if method.lower() not in {"get", "post", "put", "patch", "delete", "options", "head"} or not isinstance(operation, dict):
                continue
            method = method.upper()
            operation = resolve_local_refs(operation, document)
            responses = operation.get("responses", {})
            success_codes = sorted(str(code) for code in responses if str(code).startswith("2"))
            success_response = responses.get(success_codes[0], {}) if success_codes else {}
            response_content = success_response.get("content", {}) if isinstance(success_response, dict) else {}
            response_media = response_content.get("application/json") or next(iter(response_content.values()), {})
            response_schema = response_media.get("schema") if isinstance(response_media, dict) else None
            request_body = operation.get("requestBody", {}) if isinstance(operation.get("requestBody", {}), dict) else {}
            request_content = request_body.get("content", {})
            request_media = request_content.get("application/json") or next(iter(request_content.values()), {})
            request_schema = request_media.get("schema") if isinstance(request_media, dict) else None
            positive_body = sample_from_schema(request_schema) if isinstance(request_schema, dict) else None
            variant = "declared-success-contract"
            cases.append({"category": "CONTRACT", "title": f"{method} {endpoint} matches its declared response contract",
                          "method": method, "endpoint": endpoint, "actor": "default",
                          "input_data": {"body": positive_body} if request_schema else {},
                          "expected": {"status_codes": success_codes or ["2XX"], "schema_declared": bool(success_codes),
                                       "response_schema": response_schema},
                          "evidence": {"operation_id": operation.get("operationId"), "response_codes": sorted(map(str, responses)),
                                       "protected": bool(operation.get("security", document.get("security")))},
                          "source_path": source_path, "fingerprint": _fingerprint(source_path, "CONTRACT", method, endpoint, variant)})
            security = operation.get("security", document.get("security"))
            if security:
                variant = "unauthenticated-access-denied"
                cases.append({"category": "LOGICAL", "title": f"{method} {endpoint} rejects an unauthenticated actor",
                              "method": method, "endpoint": endpoint, "actor": "unauthenticated",
                              "input_data": {"headers": {}}, "expected": {"status_codes": ["401", "403"]},
                              "evidence": {"security_requirements": security}, "source_path": source_path,
                              "fingerprint": _fingerprint(source_path, "LOGICAL", method, endpoint, variant)})
            allowed_roles = [str(role) for role in operation.get("x-qsscope-roles", []) if str(role).strip()]
            for role in sorted(set(declared_roles) - set(allowed_roles)) if allowed_roles else []:
                variant = f"wrong-role:{role}"
                cases.append({"category": "LOGICAL", "title": f"{method} {endpoint} rejects role {role}",
                              "method": method, "endpoint": endpoint, "actor": role,
                              "input_data": {}, "expected": {"status_codes": ["403"]},
                              "evidence": {"rule_family": "WRONG_ROLE", "allowed_roles": allowed_roles,
                                           "provenance": f"{source_path}:x-qsscope-roles", "confidence": 1.0},
                              "source_path": source_path,
                              "fingerprint": _fingerprint(source_path, "LOGICAL", method, endpoint, variant)})
            ownership = operation.get("x-qsscope-ownership")
            if isinstance(ownership, dict) and ownership.get("parameter") and "other_value" in ownership:
                name = str(ownership["parameter"])
                variant = f"cross-owner:{name}"
                cases.append({"category": "LOGICAL", "title": f"{method} {endpoint} rejects cross-owner access",
                              "method": method, "endpoint": endpoint,
                              "actor": str(ownership.get("actor", "owner")),
                              "input_data": {"location": ownership.get("in", "path"), "parameter": name,
                                             "value": ownership["other_value"]},
                              "expected": {"status_codes": ["403", "404"]},
                              "evidence": {"rule_family": "CROSS_OWNER", "owner_value": ownership.get("owner_value"),
                                           "provenance": f"{source_path}:x-qsscope-ownership", "confidence": 1.0},
                              "source_path": source_path,
                              "fingerprint": _fingerprint(source_path, "LOGICAL", method, endpoint, variant)})
            transitions = operation.get("x-qsscope-state-transitions", [])
            if isinstance(transitions, list):
                for index, transition in enumerate(transitions):
                    if not isinstance(transition, dict) or "from" not in transition or "to" not in transition:
                        continue
                    valid = bool(transition.get("valid", True))
                    expected_codes = transition.get("status_codes", ["200", "204"] if valid else ["409", "422"])
                    variant = f"state:{transition['from']}:{transition['to']}:{index}"
                    cases.append({"category": "LOGICAL",
                                  "title": f"{method} {endpoint}: {transition['from']} → {transition['to']} is {'legal' if valid else 'rejected'}",
                                  "method": method, "endpoint": endpoint,
                                  "actor": str(transition.get("actor", "default")),
                                  "input_data": {"body": transition.get("body", {"state": transition["to"]})},
                                  "expected": {"status_codes": [str(code) for code in expected_codes],
                                               "source_state": transition["from"], "next_state": transition["to"],
                                               "valid_transition": valid},
                                  "evidence": {"rule_family": "STATE_TRANSITION",
                                               "provenance": f"{source_path}:x-qsscope-state-transitions[{index}]",
                                               "confidence": 1.0}, "source_path": source_path,
                                  "fingerprint": _fingerprint(source_path, "LOGICAL", method, endpoint, variant)})
            parameters = [*shared_parameters, *operation.get("parameters", [])]
            for parameter in parameters:
                if not isinstance(parameter, dict):
                    continue
                parameter = resolve_local_refs(parameter, document)
                name = str(parameter.get("name", "parameter"))
                location = str(parameter.get("in", "query"))
                schema = parameter.get("schema", {}) if isinstance(parameter.get("schema", {}), dict) else {}
                variants: list[tuple[str, Any, str]] = []
                if parameter.get("required"):
                    variants.append(("missing-required", None, "required input is rejected"))
                if "minimum" in schema:
                    variants.append(("below-minimum", schema["minimum"] - 1, "value below minimum is rejected"))
                if "maximum" in schema:
                    variants.append(("above-maximum", schema["maximum"] + 1, "value above maximum is rejected"))
                if "maxLength" in schema:
                    variants.append(("above-max-length", "x" * min(int(schema["maxLength"]) + 1, 10_001), "oversized value is rejected"))
                if schema.get("enum"):
                    variants.append(("invalid-enum", "__qsscope_invalid_enum__", "unknown enum value is rejected"))
                for variant, value, expectation in variants:
                    cases.append({"category": "EDGE", "title": f"{method} {endpoint}: {name} {variant.replace('-', ' ')}",
                                  "method": method, "endpoint": endpoint, "actor": "default",
                                  "input_data": {"location": location, "parameter": name, "value": value},
                                  "expected": {"status_codes": ["400", "422"], "behavior": expectation},
                                  "evidence": {"parameter_schema": schema, "required": bool(parameter.get("required"))},
                                  "source_path": source_path,
                                  "fingerprint": _fingerprint(source_path, "EDGE", method, endpoint, f"{name}:{variant}")})
            if request_body.get("required") and isinstance(request_schema, dict):
                cases.append({"category": "EDGE", "title": f"{method} {endpoint}: missing required request body",
                              "method": method, "endpoint": endpoint, "actor": "default",
                              "input_data": {"location": "body", "body": None},
                              "expected": {"status_codes": ["400", "415", "422"], "behavior": "missing body is rejected"},
                              "evidence": {"request_schema": request_schema}, "source_path": source_path,
                              "fingerprint": _fingerprint(source_path, "EDGE", method, endpoint, "missing-required-body")})
    return cases


def validate_loopback_base_url(base_url: str) -> str:
    parsed = urlparse(base_url)
    if parsed.scheme not in {"http", "https"} or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
        raise ValueError("Generated tests may target only an explicit loopback HTTP(S) URL")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError("Runtime base URL cannot contain credentials, query, or fragment")
    return base_url.rstrip("/")


async def execute_generated_case(client: httpx.AsyncClient, base_url: str, case: dict[str, Any],
                                 actor_headers: dict[str, str] | None = None,
                                 actor_profiles: dict[str, dict[str, str]] | None = None) -> dict[str, Any]:
    base_url = validate_loopback_base_url(base_url)
    actor = case.get("actor")
    selected_headers = dict((actor_profiles or {}).get(actor, actor_headers or {}))
    if case["category"] == "CONTRACT" and case.get("evidence", {}).get("protected") and not selected_headers:
        return {"status": "BLOCKED", "evidence": {"reason": "Protected contract case requires an actor credential profile."}}
    data = case.get("input_data", {})
    endpoint = case["endpoint"]
    parameter = data.get("parameter")
    value = data.get("value")
    if data.get("location") == "path" and value is None:
        return {"status": "NOT_APPLICABLE", "evidence": {"reason": "A missing required path segment cannot form a valid route."}}
    for placeholder in re.findall(r"\{([^}]+)\}", endpoint):
        replacement = value if data.get("location") == "path" and parameter == placeholder else 1
        endpoint = endpoint.replace("{" + placeholder + "}", str(replacement))
    params = {parameter: value} if data.get("location") == "query" and parameter and value is not None else None
    json_body = data.get("body") if "body" in data else None
    headers = {} if actor == "unauthenticated" else selected_headers
    if actor not in {None, "default", "unauthenticated"} and not headers:
        return {"status": "BLOCKED", "evidence": {"reason": f"Actor profile '{actor}' is not configured."}}
    started = time.monotonic()
    try:
        response = await client.request(case["method"], base_url + endpoint, params=params, headers=headers, json=json_body)
    except httpx.HTTPError as exc:
        return {"status": "BLOCKED", "evidence": {"reason": f"Runtime request failed: {exc.__class__.__name__}"}}
    latency_ms = int((time.monotonic() - started) * 1000)
    expected = set(case.get("expected", {}).get("status_codes", []))
    matched = str(response.status_code) in expected or ("2XX" in expected and 200 <= response.status_code < 300)
    schema_errors: list[str] = []
    response_schema = case.get("expected", {}).get("response_schema")
    if matched and isinstance(response_schema, dict):
        try:
            schema_errors = validate_json_schema(response.json(), response_schema)
        except ValueError:
            schema_errors = ["Response is not valid JSON"]
        matched = not schema_errors
    content_type = response.headers.get("content-type", "")
    evidence = {"actual_status": response.status_code, "expected_statuses": sorted(expected),
                "latency_ms": latency_ms, "content_type": content_type[:200],
                "response_bytes": len(response.content), "schema_errors": schema_errors[:100],
                "actor": actor, "source_state": case.get("expected", {}).get("source_state"),
                "expected_next_state": case.get("expected", {}).get("next_state")}
    return {"status": "PASSED" if matched else "FAILED", "evidence": evidence}
