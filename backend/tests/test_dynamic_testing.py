import httpx
import pytest
import time
from fastapi.testclient import TestClient

from app.main import app
from app.services.dynamic_testing import run_concurrency_probe, run_resilience_probe


@pytest.mark.asyncio
async def test_concurrency_detects_duplicate_success_in_disposable_write():
    async def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(201, json={"created": True})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await run_concurrency_probe(client, {
            "base_url": "http://127.0.0.1:8000", "method": "POST", "endpoint": "/last-slot",
            "request_count": 3, "json_body": {"slot": 1}, "expected_statuses": [201],
            "max_successes": 1, "disposable_confirmed": True,
        })
    assert result["status"] == "FAILED"
    assert result["evidence"]["success_count"] == 3
    assert "at most 1" in result["evidence"]["reasons"][0]


@pytest.mark.asyncio
async def test_concurrency_rejects_unconfirmed_writes_and_inconsistent_reads():
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(200))) as client:
        with pytest.raises(ValueError, match="disposable"):
            await run_concurrency_probe(client, {"base_url": "http://localhost:8000", "method": "POST",
                                                  "endpoint": "/orders", "request_count": 2})
    counter = 0

    async def changing(_request: httpx.Request) -> httpx.Response:
        nonlocal counter
        counter += 1
        return httpx.Response(200, text=str(counter))

    async with httpx.AsyncClient(transport=httpx.MockTransport(changing)) as client:
        result = await run_concurrency_probe(client, {"base_url": "http://localhost:8000", "method": "GET",
                                                       "endpoint": "/stable", "request_count": 3,
                                                       "expected_statuses": [200]})
    assert result["status"] == "FAILED"
    assert "inconsistent" in result["evidence"]["reasons"][0]


@pytest.mark.asyncio
async def test_controlled_resilience_cases_expect_safe_rejection():
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(415 if request.headers.get("content-type") == "application/octet-stream" else 400)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        outcomes = await run_resilience_probe(client, {
            "base_url": "http://127.0.0.1:8000", "method": "POST", "endpoint": "/orders",
            "disposable_confirmed": True, "cases": [
                {"kind": "INVALID_JSON", "expected_statuses": [400]},
                {"kind": "EMPTY_BODY", "expected_statuses": [400]},
                {"kind": "INVALID_CONTENT_TYPE", "expected_statuses": [415]},
            ],
        })
    assert [item["status"] for item in outcomes] == ["PASSED", "PASSED", "PASSED"]
    assert all("response_sha256" in item["evidence"] for item in outcomes)


def test_dynamic_api_enforces_loopback_and_disposable_confirmation(tmp_path):
    with TestClient(app) as client:
        project = client.post("/api/projects/discover", json={"root_path": str(tmp_path)}).json()
        external = client.post(f"/api/projects/{project['id']}/concurrency/run", json={
            "base_url": "https://example.com", "method": "GET", "endpoint": "/"})
        assert external.status_code == 422
        unsafe = client.post(f"/api/projects/{project['id']}/resilience/run", json={
            "base_url": "http://127.0.0.1:8000", "method": "POST", "endpoint": "/orders",
            "cases": [{"kind": "INVALID_JSON"}]})
        assert unsafe.status_code == 422
        assert "disposable" in unsafe.json()["error"]["message"]


def test_concurrency_api_persists_failed_case_and_finding(tmp_path, monkeypatch):
    async def failed_probe(*_args, **_kwargs):
        return {"status": "FAILED", "evidence": {"request_count": 3, "success_count": 3,
                "max_successes": 1, "reasons": ["duplicate write"]}}

    monkeypatch.setattr("app.api.routes.dynamic_tests.run_concurrency_probe", failed_probe)
    with TestClient(app) as client:
        project = client.post("/api/projects/discover", json={"root_path": str(tmp_path)}).json()
        scan = client.post(f"/api/projects/{project['id']}/scans", json={"mode": "QUICK"}).json()
        for _ in range(100):
            state = client.get(f"/api/scans/{scan['id']}").json()
            if state["status"] in {"COMPLETED", "FAILED", "ERROR"}:
                break
            time.sleep(0.03)
        response = client.post(f"/api/projects/{project['id']}/concurrency/run", json={
            "base_url": "http://127.0.0.1:8000", "method": "POST", "endpoint": "/last-slot",
            "request_count": 3, "expected_statuses": [201], "max_successes": 1,
            "disposable_confirmed": True, "scan_id": scan["id"]})
        assert response.status_code == 200
        assert response.json()["failed"] == 1
        finding = next(item for item in client.get(f"/api/scans/{scan['id']}/findings").json()
                       if item["subcategory"] == "CONCURRENCY")
        assert finding["severity"] == "HIGH"
