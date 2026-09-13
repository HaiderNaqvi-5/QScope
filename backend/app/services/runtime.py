"""Safe local scan session execution."""
from __future__ import annotations

import asyncio
import shutil
import time
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any
from datetime import datetime, timezone

from sqlalchemy import update

from app.core.database import AsyncSessionLocal
from app.models import ScanSession
from app.services.findings import deduplicate_findings, normalize_tool_output

_running: dict[str, asyncio.Task[None]] = {}
_events: dict[str, asyncio.Queue[dict[str, Any]]] = {}


def _command_for_task(task: dict[str, Any], root: Path) -> list[str] | None:
    tool = task["tool"]
    if task["task_id"] in {"discovery", "preflight"}:
        return None
    if tool == "python" and task["task_id"] == "python-compile":
        return ["python", "-m", "compileall", "-q", "."]
    if tool == "pytest" and task["task_id"] == "python-tests":
        return ["pytest", "-q"]
    if tool == "npm" and task["task_id"] == "js-lint":
        return ["npm", "run", "lint", "--if-present"]
    if tool == "semgrep" and shutil.which("semgrep"):
        return ["semgrep", "--config", "auto", "--json", "--quiet", str(root)]
    if tool == "gitleaks" and shutil.which("gitleaks"):
        return ["gitleaks", "detect", "--source", str(root), "--report-format", "json", "--report-path", "-"]
    if tool == "osv-scanner" and shutil.which("osv-scanner"):
        return ["osv-scanner", "scan", "source", "-r", str(root)]
    if tool == "trivy" and shutil.which("trivy"):
        return ["trivy", "fs", "--format", "json", "--scanners", "vuln,misconfig,secret", str(root)]
    if tool == "schemathesis" and shutil.which("schemathesis"):
        specs = sorted(root.glob("openapi.*")) + sorted(root.glob("swagger.*"))
        if specs and task.get("target", "unconfigured") != "unconfigured":
            return ["schemathesis", "run", str(specs[0]), "--base-url", task["target"]]
        if task.get("task_id") == "runtime-graphql" and task.get("target", "unconfigured") != "unconfigured":
            return ["schemathesis", "run", task["target"]]
    if tool == "newman" and shutil.which("newman") and task.get("target", "unconfigured") != "unconfigured":
        collections = sorted(root.rglob("*.postman_collection.json"))
        if collections:
            command = ["newman", "run", str(collections[0])]
            environments = sorted(root.rglob("*.postman_environment.json"))
            if environments:
                command.extend(["--environment", str(environments[0])])
            command.extend(["--env-var", f"baseUrl={task['target']}", "--reporters", "cli"])
            return command
    if tool == "playwright" and shutil.which("npx") and task.get("target", "unconfigured") != "unconfigured":
        return ["npx", "--no-install", "playwright", "test", "--reporter=line"]
    if tool == "axe" and shutil.which("npx") and task.get("target", "unconfigured") != "unconfigured":
        return ["npx", "--no-install", "playwright", "test", "--grep", "@a11y", "--reporter=line"]
    if tool == "lighthouse" and shutil.which("npx") and task.get("target", "unconfigured") != "unconfigured":
        return ["npx", "--no-install", "lighthouse", task["target"], "--output=json", "--output-path=stdout", "--quiet"]
    if tool == "zap-baseline.py" and shutil.which("zap-baseline.py") and task.get("target", "unconfigured") != "unconfigured":
        return ["zap-baseline.py", "-t", task["target"], "-J", "-"]
    if tool == "k6" and shutil.which("k6") and task.get("target", "unconfigured") != "unconfigured":
        scripts = sorted(root.glob("k6.js")) + sorted(root.glob("*.k6.js")) + sorted(root.glob("loadtest.js"))
        if scripts:
            return ["k6", "run", "--vus", "1", "--duration", "10s", str(scripts[0])]
    if tool == "jmeter" and shutil.which("jmeter") and task.get("target", "unconfigured") != "unconfigured":
        plans = sorted(root.glob("*.jmx"))
        if plans:
            return ["jmeter", "-n", "-t", str(plans[0]), "-JbaseUrl=" + task["target"], "-l", str(root / ".qsscope-jmeter-results.jtl")]
    # Security tools are never guessed or invoked with unbounded arguments.
    return None


async def _emit(session_id: str, event: dict[str, Any]) -> None:
    queue = _events.setdefault(session_id, asyncio.Queue())
    await queue.put({"session_id": session_id, **event})


async def _execute(session_id: str, project_root: str, plan: list[dict[str, Any]], approved: bool) -> None:
    results: list[dict[str, Any]] = []
    findings: list[dict[str, Any]] = []
    started = time.monotonic()
    async with AsyncSessionLocal() as db:
        now = lambda: datetime.now(timezone.utc).replace(tzinfo=None)
        await db.execute(update(ScanSession).where(ScanSession.id == session_id).values(status="RUNNING", started_at=now()))
        await db.commit()
    await _emit(session_id, {"status": "RUNNING", "message": "Scan started"})
    try:
        for task in plan:
            if task.get("requires_user_confirmation") and not approved:
                result = {"task_id": task["task_id"], "status": "SKIPPED_USER", "output": "Stage skipped because it requires explicit user confirmation."}
                result["stage"] = task["stage"]
                result["tool"] = task["tool"]
                result["target"] = task.get("target")
                results.append(result)
                await _emit(session_id, {"status": "SKIPPED_USER", "task_id": task["task_id"], "message": "Stage skipped by confirmation policy", "result": result})
                continue
            await _emit(session_id, {"status": "RUNNING", "task_id": task["task_id"], "message": f"Running {task['stage']}"})
            command = _command_for_task(task, Path(project_root))
            task_started = time.monotonic()
            if task.get("requires_runtime") and task.get("target") == "unconfigured":
                result = {"task_id": task["task_id"], "status": "SKIPPED_USER", "output": "Runtime target is not configured; confirm a localhost port before API testing."}
            elif command is None:
                result = {"task_id": task["task_id"], "status": "TOOL_MISSING" if task["tool"] in {"semgrep", "gitleaks", "osv-scanner", "schemathesis", "newman", "playwright", "axe", "lighthouse"} else "PASSED", "output": "Tool unavailable or no executable configured for this stage."}
            else:
                process = await asyncio.create_subprocess_exec(
                    *command, cwd=project_root, stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.STDOUT,
                )
                try:
                    stdout, _ = await asyncio.wait_for(process.communicate(), timeout=300)
                except asyncio.TimeoutError:
                    process.kill()
                    await process.wait()
                    result = {"task_id": task["task_id"], "status": "TIMED_OUT", "output": "Task exceeded the 300 second timeout.", "exit_code": None}
                else:
                    output = (stdout or b"").decode("utf-8", errors="replace")[-20000:]
                    result = {"task_id": task["task_id"], "status": "PASSED" if process.returncode == 0 else "FAILED", "output": output, "exit_code": process.returncode}
            result["duration_ms"] = int((time.monotonic() - task_started) * 1000)
            result["stage"] = task["stage"]
            result["tool"] = task["tool"]
            results.append(result)
            findings.extend(normalize_tool_output(session_id, result))
            await _emit(session_id, {"status": result["status"], "task_id": task["task_id"], "message": f"{task['stage']} {result['status'].lower()}", "result": result})
            if result["status"] in {"FAILED", "TIMED_OUT"}:
                break
        final_status = "FAILED" if results and results[-1]["status"] in {"FAILED", "TIMED_OUT"} else "COMPLETED"
        async with AsyncSessionLocal() as db:
            await db.execute(update(ScanSession).where(ScanSession.id == session_id).values(
                status=final_status, results=results, completed_at=now(),
            ))
            from app.models import Finding
            db.add_all([Finding(**finding) for finding in deduplicate_findings(findings)])
            await db.commit()
        await _emit(session_id, {"status": final_status, "message": f"Scan {final_status.lower()}"})
    except asyncio.CancelledError:
        async with AsyncSessionLocal() as db:
            await db.execute(update(ScanSession).where(ScanSession.id == session_id).values(status="CANCELLED", results=results, completed_at=now()))
            await db.commit()
        await _emit(session_id, {"status": "CANCELLED", "message": "Scan cancelled"})
        raise
    except Exception as exc:
        async with AsyncSessionLocal() as db:
            await db.execute(update(ScanSession).where(ScanSession.id == session_id).values(status="ERROR", results=results, error=str(exc), completed_at=now()))
            await db.commit()
        await _emit(session_id, {"status": "ERROR", "message": "Scan failed unexpectedly"})
    finally:
        _running.pop(session_id, None)
        _events.setdefault(session_id, asyncio.Queue()).put_nowait({"session_id": session_id, "status": "END", "message": "Event stream closed"})


def start_scan(session_id: str, project_root: str, plan: list[dict[str, Any]], approved: bool = False) -> None:
    _events[session_id] = asyncio.Queue()
    _running[session_id] = asyncio.create_task(_execute(session_id, project_root, plan, approved))


def cancel_scan(session_id: str) -> bool:
    task = _running.get(session_id)
    if not task:
        return False
    task.cancel()
    return True


async def event_stream(session_id: str) -> AsyncIterator[str]:
    queue = _events.setdefault(session_id, asyncio.Queue())
    while True:
        event = await queue.get()
        import json
        yield f"data: {json.dumps(event)}\n\n"
        if event["status"] == "END":
            break
