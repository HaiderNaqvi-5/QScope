"""Bounded loopback concurrency and controlled resilience probes."""
from __future__ import annotations

import asyncio
import hashlib
import time
from typing import Any

import httpx

from app.services.schema_testing import validate_loopback_base_url


def _safe_headers(headers: dict[str, str]) -> dict[str, str]:
    return {key: value for key, value in headers.items()
            if key.lower() not in {"host", "content-length", "connection"}}


async def run_concurrency_probe(client: httpx.AsyncClient, request: dict[str, Any]) -> dict[str, Any]:
    base_url = validate_loopback_base_url(request["base_url"])
    method = request["method"]
    if method not in {"GET", "HEAD"} and not request.get("disposable_confirmed"):
        raise ValueError("Concurrent write testing requires an explicitly confirmed disposable scenario")
    count = int(request.get("request_count", 3))
    if not 2 <= count <= 10:
        raise ValueError("Concurrency request count must be between 2 and 10")
    headers = _safe_headers(request.get("actor_headers", {}))

    async def one(index: int) -> dict[str, Any]:
        started = time.monotonic()
        try:
            response = await client.request(method, base_url + request["endpoint"], headers=headers,
                                            json=request.get("json_body"))
        except httpx.HTTPError as exc:
            return {"index": index, "status": "ERROR", "error": exc.__class__.__name__}
        return {"index": index, "status": response.status_code,
                "latency_ms": int((time.monotonic() - started) * 1000),
                "response_sha256": hashlib.sha256(response.content).hexdigest(),
                "response_bytes": len(response.content)}

    results = await asyncio.gather(*(one(index) for index in range(count)))
    expected = set(request.get("expected_statuses", [200]))
    successes = sum(item.get("status") in expected for item in results)
    reasons: list[str] = []
    if any(item.get("status") == "ERROR" for item in results):
        reasons.append("One or more concurrent requests failed at the transport layer.")
    max_successes = request.get("max_successes")
    if max_successes is not None and successes > max_successes:
        reasons.append(f"Observed {successes} successful writes; invariant permits at most {max_successes}.")
    if method in {"GET", "HEAD"}:
        hashes = {item.get("response_sha256") for item in results if item.get("status") in expected}
        if len(hashes) > 1:
            reasons.append("Idempotent concurrent reads returned inconsistent response bodies.")
    return {"status": "FAILED" if reasons else "PASSED", "evidence": {
        "request_count": count, "success_count": successes, "expected_statuses": sorted(expected),
        "max_successes": max_successes, "reasons": reasons, "results": results,
    }}


async def run_resilience_probe(client: httpx.AsyncClient, request: dict[str, Any]) -> list[dict[str, Any]]:
    base_url = validate_loopback_base_url(request["base_url"])
    if not request.get("disposable_confirmed"):
        raise ValueError("Resilience writes require an explicitly confirmed disposable scenario")
    headers = _safe_headers(request.get("actor_headers", {}))
    outcomes: list[dict[str, Any]] = []
    for case in request["cases"][:10]:
        kind = case["kind"]
        probe_headers = dict(headers)
        kwargs: dict[str, Any] = {}
        if kind == "INVALID_JSON":
            probe_headers["Content-Type"] = "application/json"
            kwargs["content"] = b'{"broken":'
        elif kind == "EMPTY_BODY":
            kwargs["content"] = b""
        else:
            probe_headers["Content-Type"] = "application/octet-stream"
            kwargs["content"] = b"qsscope-controlled-invalid-content"
        started = time.monotonic()
        try:
            response = await client.request(request["method"], base_url + request["endpoint"],
                                            headers=probe_headers, **kwargs)
        except httpx.HTTPError as exc:
            outcomes.append({"kind": kind, "status": "BLOCKED", "evidence": {"error": exc.__class__.__name__}})
            continue
        expected = set(case.get("expected_statuses", [400, 415, 422]))
        passed = response.status_code in expected
        outcomes.append({"kind": kind, "status": "PASSED" if passed else "FAILED", "evidence": {
            "actual_status": response.status_code, "expected_statuses": sorted(expected),
            "latency_ms": int((time.monotonic() - started) * 1000),
            "response_sha256": hashlib.sha256(response.content).hexdigest(),
            "response_bytes": len(response.content),
        }})
    return outcomes
