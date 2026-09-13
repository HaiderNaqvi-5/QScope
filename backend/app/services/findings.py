"""Normalize deterministic scan outcomes into stable findings."""
from __future__ import annotations

import hashlib
import re
from typing import Any

_LOCATION = re.compile(r"(?P<file>[^\s:]+):(?P<line>\d+)(?::\d+)?")


def normalize_result(scan_id: str, result: dict[str, Any]) -> dict[str, Any] | None:
    """Return a finding for a failed or timed-out task, never raw secrets."""
    status = result.get("status")
    if status not in {"FAILED", "TIMED_OUT"}:
        return None
    output = str(result.get("output", ""))
    match = _LOCATION.search(output)
    file_path = match.group("file") if match else None
    line = match.group("line") if match else None
    message = output.splitlines()[-1][:1000] if output else f"Task {result.get('task_id')} did not complete successfully."
    task_id = str(result.get("task_id", "unknown"))
    severity = "HIGH" if task_id in {"secrets", "sast"} else "MEDIUM"
    fingerprint = hashlib.sha256(f"{task_id}|{file_path}|{line}|{message}".encode()).hexdigest()
    return {
        "id": hashlib.sha256(f"{scan_id}|{fingerprint}".encode()).hexdigest()[:36],
        "scan_id": scan_id,
        "title": f"{task_id} {status.lower()}",
        "severity": severity,
        "tool": result.get("tool", "qsscope"),
        "stage": result.get("stage", "SCAN"),
        "file_path": file_path,
        "line": line,
        "message": message,
        "fingerprint": fingerprint,
        "status": "OPEN",
    }


def score_findings(findings: list[dict[str, Any]]) -> int:
    deductions = {"CRITICAL": 35, "HIGH": 20, "MEDIUM": 10, "LOW": 3}
    return max(0, 100 - sum(deductions.get(item.get("severity", "LOW"), 0) for item in findings))
