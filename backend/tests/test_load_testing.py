import httpx
import pytest

from app.services.findings import normalize_tool_output
from app.services.load_testing import run_conservative_load
from app.services.preflight import build_scan_plan


@pytest.mark.asyncio
async def test_generated_load_profile_records_required_metrics_without_bodies():
    async def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"sensitive-body-must-not-be-stored")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await run_conservative_load("http://127.0.0.1:8000", warmup_seconds=0,
                                             stages=((1, 0), (2, 0)), max_requests=20,
                                             client=client, requests_per_worker=2)
    metrics = result["metrics"]
    assert result["status"] == "PASSED"
    assert metrics["request_count"] == 6
    assert {"error_rate", "throughput_rps", "average_latency_ms", "p50_latency_ms",
            "p95_latency_ms", "p99_latency_ms", "max_latency_ms"} <= metrics.keys()
    assert "sensitive-body" not in str(result)


@pytest.mark.asyncio
async def test_load_failures_normalize_with_metrics():
    async def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(503)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await run_conservative_load("http://localhost:8000", warmup_seconds=0,
                                             stages=((1, 0),), client=client, requests_per_worker=2)
    findings = normalize_tool_output("scan", {"task_id": "runtime-qsscope-load", "tool": "qsscope-load",
                                                   "stage": "LOAD_TESTING", "status": result["status"],
                                                   "output": __import__("json").dumps(result)})
    assert result["status"] == "FAILED"
    assert findings[0]["evidence"]["status_counts"] == {"503": 2}
    assert findings[0]["category"] == "PERFORMANCE"


def test_full_backend_plan_generates_load_stage_without_project_plan(monkeypatch):
    monkeypatch.setattr("app.services.preflight.inspect_tools", lambda _model: [])
    _, tasks = build_scan_plan("project", {"languages": [], "backend_targets": [{"value": "FastAPI"}],
                                             "runtime_targets": [{"base_url": "http://127.0.0.1:8000"}]}, "FULL")
    task = next(item for item in tasks if item.task_id == "runtime-qsscope-load")
    assert task.target == "http://127.0.0.1:8000"
    assert task.requires_user_confirmation is True
