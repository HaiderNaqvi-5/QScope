"""Normalize deterministic scan outcomes into stable findings."""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
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
    severity = "HIGH" if task_id in {"secrets", "sast", "runtime-api", "runtime-postman", "browser-functional"} else "MEDIUM"
    title = f"{task_id} {status.lower()}"
    if task_id in {"runtime-api", "runtime-postman"}:
        target = result.get("target") or "configured local target"
        title = f"API test failed at {target}"
        message = f"Runtime API testing failed against {target}. {message}"
    elif task_id == "browser-functional":
        target = result.get("target") or "configured local target"
        title = f"Browser test failed at {target}"
        message = f"Browser testing failed against {target}. {message}"
    elif task_id in {"browser-accessibility", "browser-performance"}:
        title = f"{task_id} {status.lower()}"
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
    """Normalize structured tool output without persisting secret content."""
    tool = result.get("tool")
    if tool not in {"semgrep", "gitleaks", "trivy", "axe", "lighthouse", "newman", "schemathesis"}:
        finding = normalize_result(scan_id, result)
        return [finding] if finding else []
    try:
        payload = json.loads(str(result.get("output", "")) or "[]")
    except json.JSONDecodeError:
        finding = normalize_result(scan_id, result)
        return [finding] if finding else []
    if tool == "axe":
        findings = _normalize_axe(scan_id, result, payload)
        return findings or ([normalize_result(scan_id, result)] if normalize_result(scan_id, result) else [])
    if tool == "lighthouse":
        findings = _normalize_lighthouse(scan_id, result, payload)
        return findings or ([normalize_result(scan_id, result)] if normalize_result(scan_id, result) else [])
    if tool == "trivy":
        findings = _normalize_trivy(scan_id, result, payload)
        return findings or ([normalize_result(scan_id, result)] if normalize_result(scan_id, result) else [])
    if tool == "newman":
        findings = _normalize_newman(scan_id, result, payload)
        return findings or ([normalize_result(scan_id, result)] if normalize_result(scan_id, result) else [])
    if tool == "schemathesis":
        findings = _normalize_schemathesis(scan_id, result, payload)
        return findings or ([normalize_result(scan_id, result)] if normalize_result(scan_id, result) else [])
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


def _finding(scan_id: str, result: dict[str, Any], key: str, title: str, severity: str, message: str, path: str | None = None) -> dict[str, Any]:
    fingerprint = hashlib.sha256(f"{result.get('tool')}|{key}|{path}|{message}".encode()).hexdigest()
    return {
        "id": hashlib.sha256(f"{scan_id}|{fingerprint}".encode()).hexdigest()[:36],
        "scan_id": scan_id, "title": title, "severity": severity,
        "tool": result.get("tool", "qsscope"), "stage": result.get("stage", "BROWSER"),
        "file_path": path, "line": None, "message": message[:1000],
        "fingerprint": fingerprint, "status": "OPEN",
    }


def _normalize_axe(scan_id: str, result: dict[str, Any], payload: Any) -> list[dict[str, Any]]:
    findings = []
    for violation in payload.get("violations", []) if isinstance(payload, dict) else []:
        rule = str(violation.get("id", "axe-violation"))
        impact = str(violation.get("impact") or "moderate").lower()
        severity = {"critical": "CRITICAL", "serious": "HIGH", "moderate": "MEDIUM", "minor": "LOW"}.get(impact, "MEDIUM")
        for node in violation.get("nodes", [])[:20]:
            target = ", ".join(str(item) for item in node.get("target", []))[:300]
            summary = str(node.get("failureSummary") or violation.get("description") or "Accessibility rule failed")[:700]
            findings.append(_finding(
                scan_id, result, f"{rule}|{target}", f"Accessibility: {rule}", severity,
                f"{summary} Target: {target}" if target else summary,
            ))
    return findings


def _normalize_lighthouse(scan_id: str, result: dict[str, Any], payload: Any) -> list[dict[str, Any]]:
    findings = []
    categories = payload.get("categories", {}) if isinstance(payload, dict) else {}
    audits = payload.get("audits", {}) if isinstance(payload, dict) else {}
    for category_name, category in categories.items():
        score = category.get("score") if isinstance(category, dict) else None
        if isinstance(score, (int, float)) and score < 0.9:
            severity = "HIGH" if score < 0.5 else "MEDIUM"
            findings.append(_finding(
                scan_id, result, f"category|{category_name}", f"Lighthouse: {category_name}",
                severity, f"{category.get('title', category_name)} score is {score:.2f}.",
            ))
    for audit_id, audit in audits.items():
        if not isinstance(audit, dict) or audit.get("scoreDisplayMode") in {"notApplicable", "informative", "manual"}:
            continue
        score = audit.get("score")
        if isinstance(score, (int, float)) and score < 0.5:
            findings.append(_finding(
                scan_id, result, f"audit|{audit_id}", f"Lighthouse audit: {audit_id}",
                "MEDIUM", str(audit.get("description") or audit.get("title") or "Performance audit failed"),
            ))
    return findings


def _normalize_newman(scan_id: str, result: dict[str, Any], payload: Any) -> list[dict[str, Any]]:
    findings = []
    executions = payload.get("run", {}).get("executions", []) if isinstance(payload, dict) else []
    for execution in executions if isinstance(executions, list) else []:
        assertions = execution.get("assertions", [])
        failed = [item for item in assertions if isinstance(item, dict) and item.get("error")]
        response = execution.get("response") or {}
        request = execution.get("request") or {}
        url = request.get("url")
        if isinstance(url, dict):
            url = url.get("raw") or "/".join(str(part) for part in url.get("path", []))
        method = str(request.get("method") or "REQUEST").upper()
        status = response.get("code") or response.get("status") or "no response"
        latency = response.get("responseTime")
        if not failed and response:
            continue
        assertion_text = "; ".join(
            str(item.get("error", {}).get("message", "assertion failed"))[:300]
            for item in failed
        ) or "No response was received."
        latency_text = f"; latency {latency} ms" if isinstance(latency, (int, float)) else ""
        findings.append(_finding(
            scan_id, result, f"{method}|{url}|{status}|{assertion_text}",
            f"Newman: {method} {url or 'unknown endpoint'}", "HIGH",
            f"Observed status {status}{latency_text}. {assertion_text}. Request payload and secrets were omitted.",
        ))
    return findings


def _normalize_schemathesis(scan_id: str, result: dict[str, Any], payload: Any) -> list[dict[str, Any]]:
    findings = []
    records = payload.get("results", payload.get("cases", [])) if isinstance(payload, dict) else payload
    for case in records if isinstance(records, list) else []:
        if not isinstance(case, dict):
            continue
        status = str(case.get("status") or case.get("outcome") or "").lower()
        if status in {"success", "passed", "ok"}:
            continue
        method = str(case.get("method") or case.get("verb") or "REQUEST").upper()
        endpoint = case.get("path") or case.get("url") or "unknown endpoint"
        response = case.get("response") or {}
        code = response.get("status_code") if isinstance(response, dict) else None
        latency = case.get("elapsed") or case.get("response_time")
        latency_text = f"; latency {latency} ms" if isinstance(latency, (int, float)) else ""
        detail = str(case.get("message") or case.get("exception") or case.get("checks") or "Property or negative test failed")[:700]
        code_text = f" status {code}" if code is not None else ""
        findings.append(_finding(
            scan_id, result, f"{method}|{endpoint}|{status}|{detail}",
            f"Schemathesis: {method} {endpoint}", "HIGH",
            f"API case failed with{code_text}{latency_text}. {detail}. Payload values were omitted or redacted.",
        ))
    return findings


def _normalize_trivy(scan_id: str, result: dict[str, Any], payload: Any) -> list[dict[str, Any]]:
    findings = []
    for target in payload.get("Results", []) if isinstance(payload, dict) else []:
        target_path = target.get("Target") or target.get("Type") or "project"
        vulnerabilities = target.get("Vulnerabilities", []) or []
        misconfigurations = target.get("Misconfigurations", []) or []
        for item, category in [(entry, "vulnerability") for entry in vulnerabilities] + [
            (entry, "misconfiguration") for entry in misconfigurations
        ]:
            if not isinstance(item, dict):
                continue
            identifier = str(item.get("VulnerabilityID") or item.get("ID") or "trivy-finding")
            severity = str(item.get("Severity") or "MEDIUM").upper()
            severity = {"UNKNOWN": "LOW", "NEGLIGIBLE": "LOW"}.get(severity, severity)
            title = str(item.get("Title") or item.get("Message") or identifier)[:300]
            installed = item.get("InstalledVersion")
            fixed = item.get("FixedVersion")
            version_text = f" Installed version: {installed}." if installed else ""
            fix_text = f" Fixed version: {fixed}." if fixed else ""
            findings.append(_finding(
                scan_id,
                result,
                f"{category}|{target_path}|{identifier}",
                f"Trivy: {identifier}",
                severity if severity in {"CRITICAL", "HIGH", "MEDIUM", "LOW"} else "MEDIUM",
                f"{identifier}: {title}.{version_text}{fix_text} Secret values were omitted.",
                str(target_path),
            ))
    return findings


def deduplicate_findings(findings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Keep one finding per stable fingerprint while preserving source count."""
    unique: dict[str, dict[str, Any]] = {}
    for finding in findings:
        unique.setdefault(finding["fingerprint"], finding)
    return list(unique.values())


def analyze_code_hygiene(scan_id: str, root: Path) -> list[dict[str, Any]]:
    """Find bounded, explainable code-hygiene patterns without inferring authorship."""
    findings: list[dict[str, Any]] = []
    extensions = {".py", ".js", ".jsx", ".ts", ".tsx", ".java", ".go", ".rs", ".php", ".cs"}
    ignored = {".git", "node_modules", ".venv", "venv", "dist", "build", "coverage", ".next"}
    files_seen = 0
    for path in sorted(root.rglob("*")):
        if files_seen >= 500 or not path.is_file() or path.suffix not in extensions:
            continue
        if ignored.intersection(path.parts):
            continue
        files_seen += 1
        try:
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        for number, line in enumerate(lines[:10000], start=1):
            stripped = line.strip()
            pattern = None
            message = ""
            if re.search(r"\b(TODO|FIXME|HACK)\b", stripped, re.IGNORECASE):
                pattern = "deferred-work-marker"
                message = "Deferred-work marker found; resolve or track it before release."
            elif re.search(r"\b(console\.log|print\s*\()", stripped) and "test" not in path.name.lower():
                pattern = "debug-output"
                message = "Debug output in application code may leak implementation details or noisy diagnostics."
            elif stripped in {"pass", "..."} and number > 1:
                pattern = "empty-code-block"
                message = "Empty code block detected; make the intentional no-op explicit or implement the missing behavior."
            if pattern:
                findings.append(_finding(
                    scan_id,
                    {"tool": "qsscope", "stage": "CODE_HYGIENE"},
                    f"{pattern}|{path}|{number}",
                    f"Code hygiene: {pattern}",
                    "LOW",
                    message,
                    str(path.relative_to(root)),
                ) | {"line": str(number)})
    return findings
