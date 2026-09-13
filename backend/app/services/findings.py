"""Normalize deterministic scan outcomes into stable findings."""
from __future__ import annotations

import hashlib
import json
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
    severity = "HIGH" if task_id in {"secrets", "sast", "runtime-api", "runtime-postman"} else "MEDIUM"
    title = f"{task_id} {status.lower()}"
    if task_id in {"runtime-api", "runtime-postman"}:
        target = result.get("target") or "configured local target"
        title = f"API test failed at {target}"
        message = f"Runtime API testing failed against {target}. {message}"
    fingerprint = hashlib.sha256(f"{task_id}|{file_path}|{line}|{message}".encode()).hexdigest()
    return {
        "id": hashlib.sha256(f"{scan_id}|{fingerprint}".encode()).hexdigest()[:36],
        "scan_id": scan_id,
        "title": title,
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


def normalize_tool_output(scan_id: str, result: dict[str, Any]) -> list[dict[str, Any]]:
    """Normalize Semgrep or Gitleaks JSON without persisting secret content."""
    tool = result.get("tool")
    if tool not in {"semgrep", "gitleaks"}:
        finding = normalize_result(scan_id, result)
        return [finding] if finding else []
    try:
        payload = json.loads(str(result.get("output", "")) or "[]")
    except json.JSONDecodeError:
        return []
    records = payload.get("results", []) if isinstance(payload, dict) else payload
    normalized = []
    for record in records if isinstance(records, list) else []:
        if tool == "semgrep":
            check = record.get("check_id", "semgrep")
            message = record.get("extra", {}).get("message", "Semgrep finding")[:1000]
            path = record.get("path")
            line = str(record.get("start", {}).get("line", "")) or None
            severity = record.get("extra", {}).get("severity", "WARNING").upper()
        else:
            check = record.get("RuleID", "gitleaks")
            message = f"Secret detected by {check}; value redacted."
            path = record.get("File")
            line = str(record.get("StartLine", "")) or None
            severity = "HIGH"
        severity = {"ERROR": "HIGH", "WARNING": "MEDIUM", "INFO": "LOW"}.get(severity, severity)
        fingerprint = hashlib.sha256(f"{tool}|{check}|{path}|{line}".encode()).hexdigest()
        normalized.append({
            "id": hashlib.sha256(f"{scan_id}|{fingerprint}".encode()).hexdigest()[:36],
            "scan_id": scan_id, "title": check, "severity": severity,
            "tool": tool, "stage": result.get("stage", "STATIC_ANALYSIS"),
            "file_path": path, "line": line, "message": message,
            "fingerprint": fingerprint, "status": "OPEN",
        })
    return normalized


def deduplicate_findings(findings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Keep one finding per stable fingerprint while preserving source count."""
    unique: dict[str, dict[str, Any]] = {}
    for finding in findings:
        unique.setdefault(finding["fingerprint"], finding)
    return list(unique.values())
