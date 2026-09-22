import asyncio
import json
import time

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.browser_testing import analyze_layout, run_browser_audit
from app.services.findings import normalize_tool_output


def test_layout_analysis_reports_viewport_and_overflow():
    issues = analyze_layout({"scroll_width": 500, "small_controls": [
        {"selector": "#tiny", "width": 12, "height": 12},
    ]}, (320, 568))
    assert issues[0] == {"kind": "HORIZONTAL_OVERFLOW", "viewport": "320x568", "actual_width": 500}
    assert issues[1]["selector"] == "#tiny"


@pytest.mark.asyncio
async def test_generated_browser_probe_captures_console_responsive_and_screenshot_evidence():
    async def serve(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        await reader.read(4096)
        body = b"<html><head><title>Fixture</title></head><body style='width:500px'><button style='width:10px;height:10px'>x</button><input id='email'><script>console.error('fixture boom')</script></body></html>"
        writer.write(b"HTTP/1.1 200 OK\r\nContent-Type: text/html\r\nContent-Length: " +
                     str(len(body)).encode() + b"\r\nConnection: close\r\n\r\n" + body)
        await writer.drain()
        writer.close()

    server = await asyncio.start_server(serve, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    try:
        result, screenshots = await run_browser_audit(f"http://127.0.0.1:{port}", ((320, 568),))
    finally:
        server.close()
        await server.wait_closed()
    assert result["status"] == "FAILED", result
    assert result["console_errors"][0]["text"] == "fixture boom"
    assert any(issue["kind"] == "HORIZONTAL_OVERFLOW" for issue in result["layout_issues"])
    assert screenshots[0][0] == "browser-320x568.png"
    assert screenshots[0][1].startswith(b"\x89PNG")

    result["screenshots"] = [{"artifact_id": "shot-1", "caption": screenshots[0][0]}]
    findings = normalize_tool_output("scan-1", {"task_id": "browser-functional", "tool": "qsscope-browser",
                                                      "stage": "BROWSER_FUNCTIONAL", "status": "FAILED",
                                                      "output": json.dumps(result), "raw_artifact_id": "raw-1"})
    assert {item["subcategory"] for item in findings} >= {"CONSOLE_ERROR", "RESPONSIVE", "ACCESSIBLE_NAME"}
    responsive = next(item for item in findings if item["subcategory"] == "RESPONSIVE")
    assert responsive["evidence"]["screenshots"][0]["artifact_id"] == "shot-1"


def test_scan_runtime_persists_generated_browser_screenshot_and_finding(tmp_path, monkeypatch):
    async def fake_audit(_target):
        return ({"status": "FAILED", "target": "http://127.0.0.1:9999", "console_errors": [],
                 "page_errors": [], "failed_requests": [], "broken_links": [], "unlabeled_controls": [],
                 "layout_issues": [{"kind": "HORIZONTAL_OVERFLOW", "viewport": "320x568",
                                    "actual_width": 500}], "browser_coverage": {"chromium": "COMPLETED"}},
                [("browser-320x568.png", b"\x89PNG\r\nfixture")])

    monkeypatch.setattr("app.services.runtime.run_browser_audit", fake_audit)
    (tmp_path / "package.json").write_text(json.dumps({"dependencies": {"react": "18.2.0"}}))
    with TestClient(app) as client:
        project = client.post("/api/projects/discover", json={"root_path": str(tmp_path)}).json()
        client.post(f"/api/projects/{project['id']}/runtime-target",
                    json={"host": "127.0.0.1", "port": 9999})
        scan = client.post(f"/api/projects/{project['id']}/scans", json={"mode": "STANDARD"}).json()
        assert scan["status"] == "AWAITING_APPROVAL"
        client.post(f"/api/scans/{scan['id']}/approve")
        for _ in range(200):
            state = client.get(f"/api/scans/{scan['id']}").json()
            if state["status"] in {"COMPLETED", "FAILED", "ERROR"}:
                break
            time.sleep(0.03)
        artifacts = client.get(f"/api/scans/{scan['id']}/artifacts").json()
        screenshot = next(item for item in artifacts if item["kind"] == "SCREENSHOT")
        assert client.get(f"/api/artifacts/{screenshot['id']}/download").content.startswith(b"\x89PNG")
        findings = client.get(f"/api/scans/{scan['id']}/findings").json()
        assert any(item["subcategory"] == "RESPONSIVE" for item in findings)
