"""Safe local scan session execution."""
from __future__ import annotations

import asyncio
import json
import os
import signal
import shutil
import time
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import update

from app.core.database import AsyncSessionLocal
from app.models import FindingSource, ScanEventRecord, ScanSession, ScanTaskRecord
from app.services.findings import analyze_code_hygiene, correlate_findings, normalize_tool_output, score_findings
from app.services.artifacts import persist_binary_artifact, persist_text_artifact
from app.services.browser_testing import run_browser_audit
from app.services.load_testing import run_conservative_load
from app.services.contract_analysis import analyze_contracts
from app.services.test_results import persist_test_run
from app.services.release_gate import evaluate_release_gate

_running: dict[str, asyncio.Task[None]] = {}
_events: dict[str, asyncio.Queue[dict[str, Any]]] = {}
_start_events: dict[str, asyncio.Event] = {}
MAX_TOOL_OUTPUT_BYTES = 1_000_000
FAILED_DEPENDENCY_STATES = {"FAILED", "TIMED_OUT", "ERROR", "CANCELLED", "TOOL_ERROR", "SKIPPED_DEPENDENCY"}
SCAN_FAILURE_STATES = {"FAILED", "TIMED_OUT", "ERROR", "TOOL_ERROR"}


def _project_tool_missing(output: str) -> bool:
    """Recognize a locally unavailable package without calling it a code failure."""
    lowered = output.lower()
    return (
        "npx canceled due to missing packages" in lowered
        or "could not determine executable to run" in lowered
        or "command not found" in lowered
    )


_SYNTAX_CHECK = """import pathlib
import sys

ignored = {'.git', '.venv', 'venv', '__pycache__', 'node_modules', '.qsscope'}
errors = []
for path in pathlib.Path('.').rglob('*.py'):
    if ignored.intersection(path.parts):
        continue
    try:
        compile(path.read_bytes(), str(path), 'exec')
    except (OSError, SyntaxError, UnicodeDecodeError) as exc:
        errors.append(f'{path}: {exc}')
if errors:
    print('\\n'.join(errors))
    raise SystemExit(1)
"""


def _task_workdir(project_root: Path, task: dict[str, Any]) -> Path:
    """Resolve a manifest workspace without allowing a task to escape the project."""
    target = task.get("target", ".")
    if not isinstance(target, str) or "://" in target or target == "unconfigured":
        return project_root.resolve()
    candidate = (project_root / target).resolve()
    root = project_root.resolve()
    if candidate != root and root not in candidate.parents:
        raise ValueError(f"Task workspace escapes project root: {target}")
    if not candidate.is_dir():
        raise ValueError(f"Task workspace does not exist: {target}")
    return candidate


def _command_for_task(task: dict[str, Any], root: Path) -> list[str] | None:
    tool = task["tool"]
    if task["task_id"] in {"discovery", "preflight"}:
        return None
    if tool == "python" and task["task_id"] == "python-compile":
        # Use compile() directly rather than compileall/py_compile: both may
        # write pyc files even under -B on some Python versions.
        return ["python", "-c", _SYNTAX_CHECK]
    if tool == "pytest" and task["task_id"] == "python-tests":
        return ["pytest", "-q"]
    if task["task_id"] == "js-lint" and shutil.which("npx"):
        return ["npx", "--no-install", "eslint", ".", "--format", "json"]
    if task["task_id"] == "js-typecheck" and shutil.which("npx"):
        return ["npx", "--no-install", "tsc", "--noEmit", "--pretty", "false"]
    if task["task_id"] == "js-knip" and shutil.which("npx"):
        return ["npx", "--no-install", "knip", "--reporter", "json"]
    if tool == "npm" and task["task_id"] == "js-build":
        return ["npm", "run", "build", "--if-present"]
    if tool == "npm" and task["task_id"] == "js-tests":
        return ["npm", "test", "--", "--runInBand"]
    if task["task_id"] == "python-ruff" and shutil.which("ruff"):
        return ["ruff", "check", ".", "--output-format", "json"]
    if task["task_id"] == "python-mypy" and shutil.which("mypy"):
        return ["mypy", ".", "--no-color-output", "--show-error-codes"]
    if task["task_id"] == "java-build":
        if (root / "pom.xml").is_file() and shutil.which("mvn"):
            return ["mvn", "compile", "-DskipTests"]
        if any((root / name).is_file() for name in ("build.gradle", "build.gradle.kts")) and shutil.which("gradle"):
            return ["gradle", "classes", "--no-daemon"]
    if task["task_id"] == "java-tests":
        if (root / "pom.xml").is_file() and shutil.which("mvn"):
            return ["mvn", "test"]
        if any((root / name).is_file() for name in ("build.gradle", "build.gradle.kts")) and shutil.which("gradle"):
            return ["gradle", "test", "--no-daemon"]
    if task["task_id"] == "php-build" and shutil.which("composer"):
        return ["composer", "validate", "--no-check-publish", "--no-interaction"]
    if task["task_id"] == "php-tests" and shutil.which("php") and (root / "vendor/bin/phpunit").is_file():
        return ["php", "vendor/bin/phpunit", "--colors=never"]
    if task["task_id"] == "go-vet" and shutil.which("go"):
        return ["go", "vet", "./..."]
    if task["task_id"] == "go-tests" and shutil.which("go"):
        return ["go", "test", "-json", "./..."]
    if task["task_id"] == "go-staticcheck" and shutil.which("staticcheck"):
        return ["staticcheck", "-f", "json", "./..."]
    if task["task_id"] == "go-vuln" and shutil.which("govulncheck"):
        return ["govulncheck", "-json", "./..."]
    if task["task_id"] == "dotnet-build" and shutil.which("dotnet"):
        return ["dotnet", "build", "--no-restore", "--nologo"]
    if task["task_id"] == "dotnet-tests" and shutil.which("dotnet"):
        return ["dotnet", "test", "--no-restore", "--nologo"]
    if task["task_id"] == "rust-check" and shutil.which("cargo"):
        return ["cargo", "check", "--message-format=json"]
    if task["task_id"] == "rust-clippy" and shutil.which("cargo"):
        return ["cargo", "clippy", "--message-format=json", "--", "-D", "warnings"]
    if task["task_id"] == "rust-tests" and shutil.which("cargo"):
        return ["cargo", "test", "--", "--nocapture"]
    if task["task_id"] == "rust-audit" and shutil.which("cargo-audit"):
        return ["cargo", "audit", "--json"]
    if tool == "semgrep" and shutil.which("semgrep"):
        return ["semgrep", "--config", "auto", "--json", "--quiet", str(root)]
    if tool == "gitleaks" and shutil.which("gitleaks"):
        return ["gitleaks", "detect", "--source", str(root), "--report-format", "json", "--report-path", "-"]
    if tool == "osv-scanner" and shutil.which("osv-scanner"):
        return ["osv-scanner", "scan", "source", "-r", str(root)]
    if tool == "trivy" and shutil.which("trivy"):
        return ["trivy", "fs", "--format", "json", "--scanners", "vuln,misconfig,secret", str(root)]
    if tool == "syft" and shutil.which("syft"):
        return ["syft", f"dir:{root}", "-o", "cyclonedx-json"]
    if tool == "lizard" and shutil.which("lizard"):
        return ["lizard", "--csv", "-l", "python", "-l", "javascript", "-l", "java", "-l", "go", "-l", "rust", str(root)]
    if tool == "jscpd" and shutil.which("npx"):
        return ["npx", "--no-install", "jscpd", str(root), "--reporters", "consoleFull", "--silent"]
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
    status = event.get("status", "")
    task_id = event.get("task_id")
    if status == "RUNNING":
        event_name = "task.started" if task_id else "scan.started"
    elif status in {"FAILED", "TIMED_OUT", "TOOL_ERROR", "TOOL_MISSING"}:
        event_name = "task.failed" if task_id else "scan.failed"
    elif status == "CANCELLED":
        event_name = "scan.cancelled"
    elif status == "COMPLETED":
        event_name = "scan.completed"
    elif status == "END":
        event_name = "scan.progress"
    else:
        event_name = "task.completed" if task_id else "scan.progress"
    timestamp = datetime.now(timezone.utc).isoformat()
    envelope = {"event": event_name, "scan_id": session_id, "task_id": task_id,
                "timestamp": timestamp, "payload": event}
    async with AsyncSessionLocal() as db:
        db.add(ScanEventRecord(id=str(uuid4()), scan_id=session_id, event=event_name,
                               task_id=task_id, payload=event))
        await db.commit()
    queue = _events.setdefault(session_id, asyncio.Queue())
    await queue.put({"session_id": session_id, **event, **envelope})


async def _update_task(session_id: str, task_key: str, **values: Any) -> None:
    async with AsyncSessionLocal() as db:
        await db.execute(update(ScanTaskRecord).where(
            ScanTaskRecord.scan_id == session_id, ScanTaskRecord.task_key == task_key).values(**values))
        await db.commit()


async def _read_process_output(process: asyncio.subprocess.Process) -> bytes:
    """Drain output without allowing an analyzer to exhaust application memory."""
    retained = bytearray()
    assert process.stdout is not None
    while chunk := await process.stdout.read(65_536):
        retained.extend(chunk)
        if len(retained) > MAX_TOOL_OUTPUT_BYTES:
            del retained[:-MAX_TOOL_OUTPUT_BYTES]
    await process.wait()
    return bytes(retained)


async def _stop_process_tree(process: asyncio.subprocess.Process) -> None:
    if process.returncode is not None:
        return
    try:
        if os.name == "posix":
            os.killpg(process.pid, signal.SIGTERM)
        else:
            process.terminate()
        await asyncio.wait_for(process.wait(), timeout=2)
    except (ProcessLookupError, asyncio.TimeoutError):
        if process.returncode is None:
            try:
                if os.name == "posix":
                    os.killpg(process.pid, signal.SIGKILL)
                else:
                    process.kill()
            except ProcessLookupError:
                pass
            await process.wait()


async def _execute(session_id: str, project_root: str, plan: list[dict[str, Any]], approved: bool) -> None:
    results: list[dict[str, Any]] = []
    findings: list[dict[str, Any]] = []
    started = time.monotonic()
    async with AsyncSessionLocal() as db:
        now = lambda: datetime.now(timezone.utc).replace(tzinfo=None)
        await db.execute(update(ScanSession).where(ScanSession.id == session_id).values(status="RUNNING", started_at=now()))
        await db.commit()
    await _emit(session_id, {"status": "RUNNING", "message": "Scan started"})
    _start_events.setdefault(session_id, asyncio.Event()).set()
    try:
        task_statuses: dict[str, str] = {}
        for task in plan:
            if task.get("status") == "NOT_APPLICABLE":
                result = {"task_id": task["task_id"], "status": "NOT_APPLICABLE", "stage": task["stage"],
                          "tool": task["tool"], "target": task.get("target"),
                          "output": "Stage is not applicable or not supported for this project configuration."}
                results.append(result)
                task_statuses[task["task_id"]] = "NOT_APPLICABLE"
                await _update_task(session_id, task["task_id"], status="NOT_APPLICABLE", completed_at=now(),
                                   summary=result["output"])
                await _emit(session_id, {"status": "NOT_APPLICABLE", "task_id": task["task_id"],
                                         "message": result["output"], "result": result})
                continue
            blocked_by = [dependency for dependency in task.get("depends_on", [])
                          if task_statuses.get(dependency) in FAILED_DEPENDENCY_STATES]
            if blocked_by:
                result = {"task_id": task["task_id"], "status": "SKIPPED_DEPENDENCY", "stage": task["stage"],
                          "tool": task["tool"], "target": task.get("target"),
                          "output": "Blocked by failed prerequisite(s): " + ", ".join(blocked_by)}
                results.append(result)
                task_statuses[task["task_id"]] = "SKIPPED_DEPENDENCY"
                await _update_task(session_id, task["task_id"], status="SKIPPED_DEPENDENCY", completed_at=now(),
                                   summary=result["output"])
                await _emit(session_id, {"status": "SKIPPED_DEPENDENCY", "task_id": task["task_id"],
                                         "message": result["output"], "result": result})
                continue
            if task.get("requires_user_confirmation") and not approved:
                result = {"task_id": task["task_id"], "status": "SKIPPED_USER", "output": "Stage skipped because it requires explicit user confirmation."}
                result["stage"] = task["stage"]
                result["tool"] = task["tool"]
                result["target"] = task.get("target")
                results.append(result)
                task_statuses[task["task_id"]] = "SKIPPED_USER"
                await _update_task(session_id, task["task_id"], status="SKIPPED_USER", completed_at=now(),
                                   summary=result["output"])
                await _emit(session_id, {"status": "SKIPPED_USER", "task_id": task["task_id"], "message": "Stage skipped by confirmation policy", "result": result})
                continue
            await _emit(session_id, {"status": "RUNNING", "task_id": task["task_id"], "message": f"Running {task['stage']}"})
            await _update_task(session_id, task["task_id"], status="RUNNING", started_at=now())
            workdir = _task_workdir(Path(project_root), task)
            command = _command_for_task(task, workdir)
            task_started = time.monotonic()
            if task.get("requires_runtime") and task.get("target") == "unconfigured":
                result = {"task_id": task["task_id"], "status": "SKIPPED_USER", "output": "Runtime target is not configured; confirm a localhost port before runtime testing."}
            elif task["task_id"] == "browser-functional":
                browser_result, screenshots = await run_browser_audit(task["target"])
                screenshot_ids = []
                for filename, content in screenshots:
                    artifact = await persist_binary_artifact(
                        session_id, task["task_id"], content, filename=filename,
                        kind="SCREENSHOT", mime_type="image/png",
                    )
                    screenshot_ids.append({"artifact_id": artifact.id, "caption": filename})
                browser_result["screenshots"] = screenshot_ids
                result = {"task_id": task["task_id"], "status": browser_result["status"],
                          "output": json.dumps(browser_result), "tool": "qsscope-browser"}
            elif task["task_id"] == "runtime-qsscope-load":
                load_result = await run_conservative_load(task["target"])
                result = {"task_id": task["task_id"], "status": load_result["status"],
                          "output": json.dumps(load_result), "tool": "qsscope-load"}
            elif task["task_id"] == "contract-analysis":
                contract_issues = analyze_contracts(Path(project_root))
                result = {"task_id": task["task_id"], "status": "FAILED" if contract_issues else "PASSED",
                          "output": json.dumps({"issues": contract_issues}), "tool": "qsscope-contract"}
            elif task["task_id"] == "code-hygiene":
                hygiene_findings = analyze_code_hygiene(session_id, Path(project_root))
                findings.extend(hygiene_findings)
                result = {"task_id": task["task_id"], "status": "PASSED", "output": f"Analyzed local source files; found {len(hygiene_findings)} advisory pattern(s)."}
            elif command is None:
                core_noop = task["task_id"] in {"discovery", "preflight", "dependency-inventory"}
                result = {"task_id": task["task_id"], "status": "PASSED" if core_noop else "TOOL_MISSING",
                          "output": "Core stage completed." if core_noop else "Tool unavailable or no safe executable is configured for this applicable stage."}
            else:
                process = await asyncio.create_subprocess_exec(
                    *command, cwd=str(workdir), stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.STDOUT,
                    start_new_session=os.name == "posix",
                )
                try:
                    stdout = await asyncio.wait_for(_read_process_output(process), timeout=300)
                except asyncio.TimeoutError:
                    await _stop_process_tree(process)
                    result = {"task_id": task["task_id"], "status": "TIMED_OUT", "output": "Task exceeded the 300 second timeout.", "exit_code": None}
                except asyncio.CancelledError:
                    await _stop_process_tree(process)
                    raise
                else:
                    output = (stdout or b"").decode("utf-8", errors="replace")[-20000:]
                    status = "PASSED" if process.returncode == 0 else "FAILED"
                    if process.returncode != 0 and _project_tool_missing(output):
                        status = "TOOL_MISSING"
                    result = {"task_id": task["task_id"], "status": status, "output": output, "exit_code": process.returncode}
            result["duration_ms"] = int((time.monotonic() - task_started) * 1000)
            result["stage"] = task["stage"]
            result.setdefault("tool", task["tool"])
            results.append(result)
            artifact = await persist_text_artifact(
                session_id, task["task_id"], result.get("output", ""),
                kind="JSON" if result.get("output", "").lstrip().startswith(("{", "[")) else "LOG",
                mime_type="application/json" if result.get("output", "").lstrip().startswith(("{", "[")) else "text/plain",
            )
            result["raw_artifact_id"] = artifact.id
            if task["stage"] == "TESTS" and result["status"] in {"PASSED", "FAILED"}:
                test_run = await persist_test_run(session_id, result)
                if test_run.status == "NO_TESTS" and result["status"] == "PASSED":
                    result["status"] = "WARNING"
                    result["output"] = (result.get("output", "") + "\nQSScope: the test command completed but zero tests were discovered.").strip()
            findings.extend(normalize_tool_output(session_id, result))
            await _update_task(session_id, task["task_id"], status=result["status"], completed_at=now(),
                               exit_code=result.get("exit_code"), duration_ms=result["duration_ms"],
                               summary=result.get("output", "")[-2000:])
            await _emit(session_id, {"status": result["status"], "task_id": task["task_id"], "message": f"{task['stage']} {result['status'].lower()}", "result": result})
            task_statuses[task["task_id"]] = result["status"]
        final_status = "FAILED" if any(result["status"] in SCAN_FAILURE_STATES for result in results) else "COMPLETED"
        async with AsyncSessionLocal() as db:
            await db.execute(update(ScanSession).where(ScanSession.id == session_id).values(
                results=results,
            ))
            from app.models import Finding
            correlated = correlate_findings(findings)
            persisted_scan = await db.get(ScanSession, session_id)
            full_audit = bool(persisted_scan and persisted_scan.mode == "FULL")
            gate = evaluate_release_gate(correlated, results, full_audit=full_audit)
            score = score_findings(correlated, results, full_audit=full_audit)
            await db.execute(update(ScanSession).where(ScanSession.id == session_id).values(
                overall_score=score, is_complete_audit=gate["is_complete_audit"],
                release_readiness=gate["decision"], release_blockers=gate["blockers"],
            ))
            db.add_all([Finding(**finding) for finding in correlated])
            db.add_all([FindingSource(id=str(uuid4()), finding_id=finding["id"], tool=source["tool"],
                rule_id=source.get("rule_id"), evidence=finding.get("evidence", {}),
                raw_artifact_id=source.get("raw_artifact_id")) for finding in correlated for source in finding.get("sources", [])])
            await db.commit()
        await _emit(session_id, {"status": final_status, "message": f"Scan {final_status.lower()}"})
        # Publish terminal status only after every result, finding, source, score, gate,
        # and terminal event is durable. Consumers may tear the app down immediately
        # after observing this state, so there must be no database work left afterward.
        # Remove the task from the cancellation registry before the terminal commit:
        # once that commit is observable, only synchronous finally cleanup remains.
        _running.pop(session_id, None)
        async with AsyncSessionLocal() as db:
            await db.execute(update(ScanSession).where(ScanSession.id == session_id).values(
                status=final_status, completed_at=now(),
            ))
            await db.commit()
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
        _start_events.setdefault(session_id, asyncio.Event()).set()
        _running.pop(session_id, None)
        _events.setdefault(session_id, asyncio.Queue()).put_nowait({"session_id": session_id, "status": "END", "message": "Event stream closed"})


async def start_scan(session_id: str, project_root: str, plan: list[dict[str, Any]], approved: bool = False) -> None:
    _events[session_id] = asyncio.Queue()
    started = _start_events[session_id] = asyncio.Event()
    task = _running[session_id] = asyncio.create_task(_execute(session_id, project_root, plan, approved))
    task.add_done_callback(lambda _task: started.set())
    await asyncio.wait_for(started.wait(), timeout=10)
    _start_events.pop(session_id, None)


def cancel_scan(session_id: str) -> bool:
    task = _running.get(session_id)
    if not task:
        return False
    task.cancel()
    return True


async def shutdown_running_scans() -> None:
    """Cancel and fully drain scan jobs before the application closes its DB."""
    active = list(_running.values())
    if not active:
        return
    # Most local/fixture scans are finishing their final durable transaction when
    # shutdown begins. Give them a brief grace period so cancellation cannot land
    # in the middle of an aiosqlite write and leave a database lock behind.
    done, pending = await asyncio.wait(active, timeout=2)
    del done
    for task in pending:
        task.cancel()
    if pending:
        await asyncio.gather(*pending, return_exceptions=True)


async def event_stream(session_id: str) -> AsyncIterator[str]:
    queue = _events.setdefault(session_id, asyncio.Queue())
    while True:
        event = await queue.get()
        import json
        yield f"data: {json.dumps(event)}\n\n"
        if event["status"] == "END":
            break
