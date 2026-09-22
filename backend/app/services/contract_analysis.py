"""Deterministic static frontend-to-OpenAPI contract drift analysis."""
from __future__ import annotations

from pathlib import Path
import re
from typing import Any

from app.services.schema_testing import load_openapi, resolve_local_refs

_FETCH = re.compile(r"fetch\(\s*['\"`]([^'\"`?]+)[^'\"`]*['\"`]\s*(?:,\s*\{(?P<options>.{0,800}?)\})?\s*\)", re.DOTALL)
_METHOD = re.compile(r"method\s*:\s*['\"]([A-Za-z]+)['\"]")
_FIELD = re.compile(r"\b(?:data|json|result|response)\.([A-Za-z_$][\w$]*)")
_JSON_BODY = re.compile(r"JSON\.stringify\(\s*\{(.{0,1500}?)\}\s*\)", re.DOTALL)
_OBJECT_KEY = re.compile(r"(?:^|[,\s])([A-Za-z_$][\w$]*)\s*:")


def _route_pattern(route: str) -> re.Pattern[str]:
    escaped = re.escape(route)
    escaped = re.sub(r"\\\{[^}]+\\\}", r"[^/]+", escaped)
    return re.compile(rf"(?:https?://[^/]+)?{escaped}$")


def _response_fields(operation: dict[str, Any], document: dict[str, Any]) -> set[str]:
    responses = operation.get("responses", {})
    success = next((value for key, value in responses.items() if str(key).startswith("2")), {})
    success = resolve_local_refs(success, document) if isinstance(success, dict) else {}
    content = success.get("content", {})
    media = content.get("application/json") or next(iter(content.values()), {})
    schema = resolve_local_refs(media.get("schema", {}), document) if isinstance(media, dict) else {}
    if schema.get("type") == "array":
        schema = schema.get("items", {})
    return set(schema.get("properties", {})) if isinstance(schema, dict) else set()


def _request_contract(operation: dict[str, Any], document: dict[str, Any]) -> tuple[set[str], set[str]]:
    body = resolve_local_refs(operation.get("requestBody", {}), document)
    content = body.get("content", {}) if isinstance(body, dict) else {}
    media = content.get("application/json") or next(iter(content.values()), {})
    schema = resolve_local_refs(media.get("schema", {}), document) if isinstance(media, dict) else {}
    return (set(schema.get("properties", {})), set(schema.get("required", []))) if isinstance(schema, dict) else (set(), set())


def analyze_contracts(root: Path) -> list[dict[str, Any]]:
    specs = sorted(path for pattern in ("openapi.json", "openapi.yaml", "openapi.yml", "swagger.json", "swagger.yaml")
                   for path in root.rglob(pattern))
    operations: list[tuple[str, str, set[str], str, set[str], set[str]]] = []
    for spec in specs[:20]:
        try:
            document = load_openapi(spec)
        except (OSError, ValueError):
            continue
        for route, path_item in document.get("paths", {}).items():
            for method, operation in path_item.items() if isinstance(path_item, dict) else []:
                if method.upper() in {"GET", "POST", "PUT", "PATCH", "DELETE"} and isinstance(operation, dict):
                    request_fields, required_fields = _request_contract(operation, document)
                    operations.append((method.upper(), route, _response_fields(operation, document),
                                       spec.relative_to(root).as_posix(), request_fields, required_fields))
    issues: list[dict[str, Any]] = []
    ignored = {"node_modules", ".next", "dist", "build", ".git", ".qsscope"}
    sources = sorted(path for suffix in ("*.ts", "*.tsx", "*.js", "*.jsx") for path in root.rglob(suffix)
                     if not ignored.intersection(path.relative_to(root).parts))
    for source in sources[:10_000]:
        text = source.read_text(encoding="utf-8", errors="ignore")[:2_000_000]
        for match in _FETCH.finditer(text):
            url = match.group(1)
            options = match.group("options") or ""
            # The lightweight fetch matcher intentionally bounds its scan, but a
            # nested object literal can end the captured options at the inner
            # brace. Inspect the complete nearby call for JSON body shape.
            call_window = text[match.start():match.start() + 2_000]
            method_match = _METHOD.search(options)
            method = method_match.group(1).upper() if method_match else "GET"
            matching_routes = [item for item in operations if _route_pattern(item[1]).match(url)]
            line = text.count("\n", 0, match.start()) + 1
            if not matching_routes:
                issues.append({"kind": "ROUTE_MISMATCH", "frontend_file": source.relative_to(root).as_posix(),
                               "frontend_line": line, "method": method, "endpoint": url,
                               "api_spec": None, "message": "Frontend route is absent from detected OpenAPI contracts."})
                continue
            operation = next((item for item in matching_routes if item[0] == method), None)
            if operation is None:
                issues.append({"kind": "METHOD_MISMATCH", "frontend_file": source.relative_to(root).as_posix(),
                               "frontend_line": line, "method": method, "endpoint": url,
                               "api_spec": matching_routes[0][3], "declared_methods": sorted({item[0] for item in matching_routes}),
                               "message": "Frontend HTTP method is absent from the matching OpenAPI route."})
                continue
            body_match = _JSON_BODY.search(call_window)
            if body_match and operation[4]:
                supplied = set(_OBJECT_KEY.findall(body_match.group(1)))
                for field in sorted(supplied - operation[4]):
                    issues.append({"kind": "REQUEST_FIELD_MISMATCH", "frontend_file": source.relative_to(root).as_posix(),
                                   "frontend_line": line, "method": method, "endpoint": url,
                                   "api_spec": operation[3], "field": field,
                                   "declared_fields": sorted(operation[4]),
                                   "message": f"Frontend sends request field '{field}' absent from the OpenAPI schema."})
                missing = sorted(operation[5] - supplied)
                if missing:
                    issues.append({"kind": "MISSING_REQUIRED_REQUEST_FIELDS", "frontend_file": source.relative_to(root).as_posix(),
                                   "frontend_line": line, "method": method, "endpoint": url,
                                   "api_spec": operation[3], "missing_fields": missing,
                                   "declared_fields": sorted(operation[4]),
                                   "message": "Frontend request omits required OpenAPI field(s): " + ", ".join(missing)})
            window = text[match.end():match.end() + 1800]
            expected_fields = operation[2]
            referenced_fields = set(_FIELD.findall(window)) - {"json", "text", "blob", "status", "ok", "headers"}
            for field in sorted(referenced_fields - expected_fields) if expected_fields else []:
                issues.append({"kind": "RESPONSE_FIELD_MISMATCH", "frontend_file": source.relative_to(root).as_posix(),
                               "frontend_line": line, "method": method, "endpoint": url,
                               "api_spec": operation[3], "field": field,
                               "declared_fields": sorted(expected_fields),
                               "message": f"Frontend reads response field '{field}' absent from the OpenAPI schema."})
    return issues
