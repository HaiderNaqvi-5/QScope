"""Conservative QSScope-owned loopback load and latency probe."""
from __future__ import annotations

import asyncio
import math
import time
from typing import Any

import httpx

from app.services.schema_testing import validate_loopback_base_url

DEFAULT_STAGES = ((1, 10), (10, 10), (25, 30))


def _percentile(values: list[float], percentile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, math.ceil(percentile * len(ordered)) - 1))
    return round(ordered[index], 2)


async def run_conservative_load(
    target: str, *, warmup_seconds: int = 10,
    stages: tuple[tuple[int, int], ...] = DEFAULT_STAGES, max_requests: int = 5_000,
    client: httpx.AsyncClient | None = None, requests_per_worker: int | None = None,
) -> dict[str, Any]:
    """Issue bounded GET requests only; never submit mutating traffic."""
    target = validate_loopback_base_url(target)
    latencies: list[float] = []
    errors = 0
    statuses: dict[str, int] = {}
    lock = asyncio.Lock()
    owned_client = client is None
    if client is None:
        client = httpx.AsyncClient(timeout=httpx.Timeout(10, connect=3), follow_redirects=False)

    async def request_once() -> None:
        nonlocal errors
        if len(latencies) >= max_requests:
            return
        started = time.monotonic()
        status = "TRANSPORT_ERROR"
        failed = True
        try:
            response = await client.get(target)
            status = str(response.status_code)
            failed = not 200 <= response.status_code < 400
        except httpx.HTTPError:
            pass
        latency = (time.monotonic() - started) * 1000
        async with lock:
            if len(latencies) < max_requests:
                latencies.append(latency)
                statuses[status] = statuses.get(status, 0) + 1
                errors += int(failed)

    async def worker(deadline: float, fixed_count: int | None) -> None:
        count = 0
        while len(latencies) < max_requests and ((fixed_count is not None and count < fixed_count) or
                                                  (fixed_count is None and time.monotonic() < deadline)):
            await request_once()
            count += 1

    started = time.monotonic()
    try:
        if requests_per_worker is None and warmup_seconds:
            await worker(time.monotonic() + warmup_seconds, None)
        stage_evidence = []
        for virtual_users, duration in stages:
            before = len(latencies)
            deadline = time.monotonic() + duration
            await asyncio.gather(*(worker(deadline, requests_per_worker) for _ in range(virtual_users)))
            stage_evidence.append({"virtual_users": virtual_users, "duration_seconds": duration,
                                   "requests": len(latencies) - before})
            if len(latencies) >= max_requests:
                break
    finally:
        if owned_client:
            await client.aclose()
    elapsed = max(time.monotonic() - started, 0.000001)
    count = len(latencies)
    metrics = {
        "request_count": count, "error_count": errors,
        "error_rate": round(errors / count, 4) if count else 1.0,
        "throughput_rps": round(count / elapsed, 2),
        "average_latency_ms": round(sum(latencies) / count, 2) if count else 0.0,
        "p50_latency_ms": _percentile(latencies, 0.50), "p95_latency_ms": _percentile(latencies, 0.95),
        "p99_latency_ms": _percentile(latencies, 0.99), "max_latency_ms": round(max(latencies), 2) if latencies else 0.0,
        "status_counts": statuses, "stages": stage_evidence, "warmup_seconds": warmup_seconds,
        "bounded_request_cap": max_requests, "method": "GET", "target": target,
    }
    return {"status": "PASSED" if count and errors == 0 else "FAILED", "metrics": metrics,
            "message": "Conservative loopback load profile completed without response-body persistence."}
