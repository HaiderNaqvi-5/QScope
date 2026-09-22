"""Normalize native test-run summaries without claiming zero tests passed."""
from __future__ import annotations

import json
import re
from typing import Any
from uuid import uuid4

from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.models import ScanTaskRecord, TestRun

COUNT_PATTERNS = {
    "passed": re.compile(r"(\d+)\s+passed", re.IGNORECASE),
    "failed": re.compile(r"(\d+)\s+failed", re.IGNORECASE),
    "skipped": re.compile(r"(\d+)\s+skipped", re.IGNORECASE),
    "tests": re.compile(r"Tests:\s*(?:(\d+)\s+failed,?\s*)?(?:(\d+)\s+passed,?\s*)?(\d+)\s+total", re.IGNORECASE),
}
COVERAGE_PATTERNS = (
    re.compile(r"TOTAL\s+\d+\s+\d+\s+(\d+(?:\.\d+)?)%", re.IGNORECASE),
    re.compile(r"(?:line|lines?)\s+coverage\s*[:=]\s*(\d+(?:\.\d+)?)%", re.IGNORECASE),
    re.compile(r"All files\s*\|(?:[^|]*\|){2}\s*(\d+(?:\.\d+)?)", re.IGNORECASE),
)


def parse_test_summary(task_id: str, output: str, exit_status: str) -> dict[str, Any]:
    framework = ("pytest" if task_id == "python-tests" else "go test" if task_id == "go-tests"
                 else "dotnet test" if task_id == "dotnet-tests" else "cargo test" if task_id == "rust-tests"
                 else "PHPUnit" if task_id == "php-tests" else "Maven/Gradle" if task_id == "java-tests" else "Jest/Vitest")
    counts = {name: sum(int(match) for match in pattern.findall(output) if isinstance(match, str))
              for name, pattern in COUNT_PATTERNS.items() if name != "tests"}
    if task_id == "go-tests":
        events = []
        for line in output.splitlines():
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if event.get("Test") and event.get("Action") in {"pass", "fail", "skip"}:
                events.append(event)
        counts = {name: sum(1 for event in events if event["Action"] == action)
                  for name, action in (("passed", "pass"), ("failed", "fail"), ("skipped", "skip"))}
    jest = COUNT_PATTERNS["tests"].search(output)
    junit = re.search(
        r"Tests run:\s*(\d+),\s*Failures:\s*(\d+),\s*Errors:\s*(\d+),\s*Skipped:\s*(\d+)",
        output, re.IGNORECASE,
    )
    cargo = re.search(
        r"test result:\s*\w+\.\s*(\d+) passed;\s*(\d+) failed;\s*(\d+) ignored",
        output, re.IGNORECASE,
    )
    if jest:
        counts = {"failed": int(jest.group(1) or 0), "passed": int(jest.group(2) or 0), "skipped": 0}
        discovered = int(jest.group(3))
    elif junit:
        discovered, reported_failures, errors, skipped = map(int, junit.groups())
        failed = reported_failures + errors
        counts = {"passed": max(0, discovered - failed - skipped), "failed": failed, "skipped": skipped}
    elif cargo:
        passed, failed, skipped = map(int, cargo.groups())
        counts = {"passed": passed, "failed": failed, "skipped": skipped}
        discovered = passed + failed + skipped
    else:
        discovered = sum(counts.values())
    status = "FAILED" if exit_status == "FAILED" or counts.get("failed", 0) else "PASSED"
    if discovered == 0:
        status = "NO_TESTS"
    summary = {"framework": framework, "discovered": discovered, **counts, "status": status}
    for pattern in COVERAGE_PATTERNS:
        coverage = pattern.search(output)
        if coverage:
            summary["coverage_percent"] = str(float(coverage.group(1)))
            break
    return summary


async def persist_test_run(scan_id: str, result: dict[str, Any]) -> TestRun:
    summary = parse_test_summary(result["task_id"], result.get("output", ""), result["status"])
    async with AsyncSessionLocal() as db:
        task = (await db.execute(select(ScanTaskRecord).where(
            ScanTaskRecord.scan_id == scan_id, ScanTaskRecord.task_key == result["task_id"]))).scalars().first()
        run = TestRun(id=str(uuid4()), scan_id=scan_id, task_id=task.id if task else None,
            suite_name=result["task_id"], framework=summary["framework"], discovered=summary["discovered"],
            passed=summary.get("passed", 0), failed=summary.get("failed", 0), skipped=summary.get("skipped", 0),
            duration_ms=result.get("duration_ms"), coverage_percent=summary.get("coverage_percent"),
            status=summary["status"], raw_artifact_id=result.get("raw_artifact_id"),
            details={"exit_code": result.get("exit_code")})
        db.add(run)
        await db.commit()
        await db.refresh(run)
        return run
