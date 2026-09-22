"""Normalize deterministic scan outcomes into stable findings."""
from __future__ import annotations

import hashlib
import csv
import io
import json
import re
from pathlib import Path
from typing import Any

_LOCATION = re.compile(r"(?P<file>[^\s:]+):(?P<line>\d+)(?::\d+)?")
CATEGORY_WEIGHTS = {
    "SECURITY": 20, "CODE_QUALITY": 15, "TESTS": 15, "DEPENDENCIES": 10,
    "API_RELIABILITY": 10, "FRONTEND": 10, "ACCESSIBILITY": 5,
    "PERFORMANCE": 10, "REGRESSION": 5,
}
PENALTIES = {"CRITICAL": 25, "HIGH": 12, "MEDIUM": 5, "LOW": 2, "INFO": 0, "ADVISORY": 0}


def _category(stage: str) -> str:
    stage = stage.upper()
    if stage in {"SAST", "SECRETS", "DAST", "CONTAINER_SECURITY"}:
        return "SECURITY"
    if stage in {"TESTS", "COVERAGE"}:
        return "TESTS"
    if "DEPENDENCY" in stage or stage == "SBOM":
        return "DEPENDENCIES"
    if "API" in stage or "GRAPHQL" in stage:
        return "API_RELIABILITY"
    if stage in {"BROWSER", "BROWSER_FUNCTIONAL", "RESPONSIVE"}:
        return "FRONTEND"
    if stage == "ACCESSIBILITY":
        return "ACCESSIBILITY"
    if stage in {"PERFORMANCE", "LOAD_TESTING"}:
        return "PERFORMANCE"
    if stage == "REGRESSION":
        return "REGRESSION"
    return "CODE_QUALITY"


def complete_finding(finding: dict[str, Any]) -> dict[str, Any]:
    """Fill canonical fields only from deterministic evidence; never fabricate source facts."""
    stage = str(finding.get("stage", "CODE_QUALITY"))
    line = finding.get("line")
    try:
        numeric_line = int(line) if line else None
    except (TypeError, ValueError):
        numeric_line = None
    tool = str(finding.get("tool", "qsscope"))
    title = str(finding.get("title", "Finding"))
    message = str(finding.get("message", ""))
    finding.setdefault("category", _category(stage))
    finding.setdefault("subcategory", stage)
    finding.setdefault("description", message)
    finding.setdefault("confidence", "0.98" if stage in {"BUILD_TYPECHECK", "TESTS"} else "0.85")
    finding.setdefault("rule_id", title)
    finding.setdefault("start_line", numeric_line)
    finding.setdefault("end_line", numeric_line)
    finding.setdefault("endpoint", finding.get("target") if finding["category"] == "API_RELIABILITY" else None)
    finding.setdefault("evidence", {"message": message, "location": finding.get("file_path"), "line": numeric_line})
    finding.setdefault("raw_artifact_id", finding.get("raw_artifact_id"))
    finding.setdefault("why_it_matters", "This issue reduces the verified quality or release confidence of the project.")
    finding.setdefault("recommendation", "Review the cited evidence, correct the underlying issue, and rerun the detecting check.")
    finding.setdefault("suggested_patch", None)
    finding.setdefault("suggested_test", None)
    finding.setdefault("sources", [{"tool": tool, "rule_id": finding.get("rule_id"),
                                    "raw_artifact_id": finding.get("raw_artifact_id")}])
    location = finding.get("endpoint") or f"{finding.get('file_path')}:{numeric_line}"
    finding.setdefault("correlation_key", hashlib.sha256(
        f"{finding['category']}|{finding.get('subcategory')}|{location}".encode()).hexdigest())
    return finding


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
    return complete_finding({
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
        "raw_artifact_id": result.get("raw_artifact_id"),
    })


def score_findings(findings: list[dict[str, Any]], task_results: list[dict[str, Any]] | None = None,
                   *, full_audit: bool = False) -> int:
    """Apply locked category penalties, proportional applicability, and release caps."""
    canonical = [complete_finding(dict(item)) for item in findings
                 if item.get("status", "OPEN") not in {"VERIFIED_FIXED", "FALSE_POSITIVE"}]
    applicable = {item["category"] for item in canonical} or {"CODE_QUALITY"}
    category_scores = {category: 100 for category in applicable}
    seen: set[str] = set()
    for item in canonical:
        fingerprint = str(item.get("fingerprint") or item.get("correlation_key"))
        if fingerprint in seen:
            continue
        seen.add(fingerprint)
        category = item["category"]
        category_scores[category] = max(0, category_scores[category] - PENALTIES.get(str(item.get("severity")), 0))
    total_weight = sum(CATEGORY_WEIGHTS.get(category, 0) for category in applicable) or 1
    score = round(sum(category_scores[category] * CATEGORY_WEIGHTS.get(category, 0)
                      for category in applicable) / total_weight)
    if any(item["category"] == "SECURITY" and item.get("severity") == "CRITICAL" for item in canonical):
        score = min(score, 59)
    results = task_results or []
    if any(item.get("stage") == "BUILD_TYPECHECK" and item.get("status") == "FAILED" for item in results):
        score = min(score, 39)
    if any(item.get("stage") == "TESTS" and item.get("status") == "FAILED" for item in results):
        score = min(score, 69)
    if any(item.get("stage") == "SECRETS" and item.get("status") == "FAILED" for item in results):
        score = min(score, 49)
    return score


def normalize_tool_output(scan_id: str, result: dict[str, Any]) -> list[dict[str, Any]]:
    """Normalize structured tool output without persisting secret content."""
    tool = result.get("tool")
    if tool == "lizard":
        return _normalize_lizard(scan_id, result)
    if tool == "jscpd":
        return _normalize_jscpd(scan_id, result)
    if tool not in {"semgrep", "gitleaks", "trivy", "osv-scanner", "syft", "axe", "lighthouse", "newman", "schemathesis", "qsscope-browser", "qsscope-load", "qsscope-contract"}:
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
    if tool == "qsscope-browser":
        return _normalize_browser(scan_id, result, payload)
    if tool == "qsscope-load":
        metrics = payload.get("metrics", {}) if isinstance(payload, dict) else {}
        if result.get("status") != "FAILED":
            return []
        fingerprint = hashlib.sha256(
            f"qsscope-load|{metrics.get('target')}|{metrics.get('error_rate')}".encode()).hexdigest()
        return [complete_finding({
            "id": hashlib.sha256(f"{scan_id}|{fingerprint}".encode()).hexdigest()[:36],
            "scan_id": scan_id, "title": "Conservative load profile observed request failures",
            "severity": "HIGH" if float(metrics.get("error_rate", 0)) >= 0.1 else "MEDIUM",
            "tool": "qsscope-load", "stage": "LOAD_TESTING", "category": "PERFORMANCE",
            "subcategory": "LOAD_RELIABILITY", "message":
                f"Error rate {metrics.get('error_rate', 1):.2%}; P95 {metrics.get('p95_latency_ms', 0)} ms.",
            "endpoint": metrics.get("target"), "evidence": metrics,
            "raw_artifact_id": result.get("raw_artifact_id"), "fingerprint": fingerprint, "status": "OPEN",
        })]
    if tool == "qsscope-contract":
        findings = []
        for issue in payload.get("issues", []) if isinstance(payload, dict) else []:
            fingerprint = hashlib.sha256(
                f"contract|{issue.get('kind')}|{issue.get('frontend_file')}|{issue.get('method')}|{issue.get('endpoint')}|{issue.get('field')}".encode()).hexdigest()
            findings.append(complete_finding({
                "id": hashlib.sha256(f"{scan_id}|{fingerprint}".encode()).hexdigest()[:36],
                "scan_id": scan_id, "title": f"Frontend/backend contract: {issue.get('kind')}",
                "severity": "HIGH" if issue.get("kind") in {"ROUTE_MISMATCH", "METHOD_MISMATCH"} else "MEDIUM",
                "tool": "qsscope-contract", "stage": "CONTRACT_TESTING", "category": "API_RELIABILITY",
                "subcategory": issue.get("kind"), "file_path": issue.get("frontend_file"),
                "line": str(issue.get("frontend_line")) if issue.get("frontend_line") else None,
                "endpoint": f"{issue.get('method')} {issue.get('endpoint')}",
                "message": issue.get("message", "Contract drift detected."), "evidence": issue,
                "raw_artifact_id": result.get("raw_artifact_id"), "fingerprint": fingerprint, "status": "OPEN",
            }))
        return findings
    if tool == "trivy":
        findings = _normalize_trivy(scan_id, result, payload)
        return findings or ([normalize_result(scan_id, result)] if normalize_result(scan_id, result) else [])
    if tool == "osv-scanner":
        findings = _normalize_osv(scan_id, result, payload)
        return findings or ([normalize_result(scan_id, result)] if normalize_result(scan_id, result) else [])
    if tool == "syft":
        return []
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
        normalized.append(complete_finding({
            "id": hashlib.sha256(f"{scan_id}|{fingerprint}".encode()).hexdigest()[:36],
            "scan_id": scan_id, "title": check, "severity": severity,
            "tool": tool, "stage": result.get("stage", "STATIC_ANALYSIS"),
            "file_path": path, "line": line, "message": message,
            "fingerprint": fingerprint, "status": "OPEN",
            "raw_artifact_id": result.get("raw_artifact_id"),
        }))
    return normalized


def _finding(scan_id: str, result: dict[str, Any], key: str, title: str, severity: str, message: str, path: str | None = None) -> dict[str, Any]:
    fingerprint = hashlib.sha256(f"{result.get('tool')}|{key}|{path}|{message}".encode()).hexdigest()
    return complete_finding({
        "id": hashlib.sha256(f"{scan_id}|{fingerprint}".encode()).hexdigest()[:36],
        "scan_id": scan_id, "title": title, "severity": severity,
        "tool": result.get("tool", "qsscope"), "stage": result.get("stage", "BROWSER"),
        "file_path": path, "line": None, "message": message[:1000],
        "fingerprint": fingerprint, "status": "OPEN",
        "raw_artifact_id": result.get("raw_artifact_id"),
    })


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


def _normalize_browser(scan_id: str, result: dict[str, Any], payload: Any) -> list[dict[str, Any]]:
    if not isinstance(payload, dict):
        return []
    findings: list[dict[str, Any]] = []
    screenshots = payload.get("screenshots", [])
    groups = (
        ("console_errors", "Browser console error", "MEDIUM", "CONSOLE_ERROR"),
        ("page_errors", "Unhandled browser page error", "HIGH", "PAGE_ERROR"),
        ("failed_requests", "Browser network request failed", "MEDIUM", "NETWORK_FAILURE"),
        ("layout_issues", "Responsive layout issue", "MEDIUM", "RESPONSIVE"),
        ("broken_links", "Broken internal navigation", "MEDIUM", "BROKEN_NAVIGATION"),
        ("unlabeled_controls", "Form control lacks an accessible label", "HIGH", "ACCESSIBLE_NAME"),
    )
    for field, title, severity, subcategory in groups:
        for index, issue in enumerate(payload.get(field, [])[:100]):
            detail = issue if isinstance(issue, dict) else {"message": str(issue)}
            fingerprint = hashlib.sha256(
                f"qsscope-browser|{field}|{json.dumps(detail, sort_keys=True)}".encode()).hexdigest()
            findings.append(complete_finding({
                "id": hashlib.sha256(f"{scan_id}|{fingerprint}".encode()).hexdigest()[:36],
                "scan_id": scan_id, "title": title, "severity": severity,
                "tool": "qsscope-browser", "stage": "BROWSER_FUNCTIONAL",
                "category": "API_RELIABILITY" if field in {"failed_requests", "broken_links"} else
                            "ACCESSIBILITY" if field in {"layout_issues", "unlabeled_controls"} else "CODE_QUALITY",
                "subcategory": subcategory, "message": json.dumps(detail, default=str)[:1000],
                "evidence": {"target": payload.get("target"), "issue": detail,
                             "screenshots": screenshots, "index": index},
                "raw_artifact_id": result.get("raw_artifact_id"), "fingerprint": fingerprint,
                "status": "OPEN",
            }))
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


def _normalize_osv(scan_id: str, result: dict[str, Any], payload: Any) -> list[dict[str, Any]]:
    findings = []
    for scan_result in payload.get("results", []) if isinstance(payload, dict) else []:
        source = scan_result.get("source", {}).get("path", "manifest")
        for package in scan_result.get("packages", []):
            package_info = package.get("package", {})
            name = package_info.get("name", "unknown package")
            version = package_info.get("version", "unknown")
            for vulnerability in package.get("vulnerabilities", []):
                identifier = vulnerability.get("id", "OSV advisory")
                summary = vulnerability.get("summary") or vulnerability.get("details") or "Known vulnerability"
                findings.append(_finding(scan_id, result, f"{identifier}|{name}|{version}",
                    f"{identifier} affects {name}", "HIGH", f"{name} {version}: {str(summary)[:700]}", source))
    return findings


def _normalize_lizard(scan_id: str, result: dict[str, Any]) -> list[dict[str, Any]]:
    findings = []
    try:
        rows = csv.DictReader(io.StringIO(str(result.get("output", ""))))
        for row in rows:
            complexity = int(row.get("CCN", "0") or 0)
            length = int(row.get("NLOC", "0") or 0)
            if complexity <= 15 and length <= 100:
                continue
            path = row.get("file") or row.get("filename")
            line = row.get("start line") or row.get("line")
            severity = "HIGH" if complexity > 30 else "MEDIUM"
            finding = _finding(scan_id, result, f"{path}|{line}|{row.get('function_name')}",
                f"Complex function: {row.get('function_name') or 'unknown'}", severity,
                f"Cyclomatic complexity is {complexity}; function length is {length} lines.", path)
            finding["line"] = line
            finding["start_line"] = int(line) if line and line.isdigit() else None
            findings.append(finding)
    except (csv.Error, TypeError, ValueError):
        return []
    return findings


def _normalize_jscpd(scan_id: str, result: dict[str, Any]) -> list[dict[str, Any]]:
    findings = []
    output = str(result.get("output", ""))
    pattern = re.compile(r"(?P<first>[^\s:]+):(?P<line>\d+).*?(?P<second>[^\s:]+):\d+", re.IGNORECASE)
    for index, match in enumerate(pattern.finditer(output)):
        if index >= 100:
            break
        findings.append(_finding(scan_id, result, f"{match.group('first')}|{match.group('second')}|{match.group('line')}",
            "Duplicated code block", "MEDIUM", f"Similar code appears in {match.group('first')} and {match.group('second')}.",
            match.group("first")) | {"line": match.group("line")})
    return findings


def deduplicate_findings(findings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Keep one finding per stable fingerprint while preserving source count."""
    unique: dict[str, dict[str, Any]] = {}
    for finding in findings:
        finding = complete_finding(finding)
        existing = unique.get(finding["fingerprint"])
        if existing is None:
            unique[finding["fingerprint"]] = finding
        else:
            existing_sources = {(source.get("tool"), source.get("rule_id")) for source in existing.get("sources", [])}
            existing["sources"].extend(source for source in finding.get("sources", [])
                                       if (source.get("tool"), source.get("rule_id")) not in existing_sources)
    return list(unique.values())


def correlate_findings(findings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Group deterministic same-location issues while preserving every source."""
    severity_rank = {"CRITICAL": 5, "HIGH": 4, "MEDIUM": 3, "LOW": 2, "INFO": 1, "ADVISORY": 0}
    groups: dict[str, dict[str, Any]] = {}
    for finding in deduplicate_findings(findings):
        key = finding["correlation_key"]
        existing = groups.get(key)
        if existing is None:
            groups[key] = finding
            continue
        source_keys = {(source.get("tool"), source.get("rule_id")) for source in existing["sources"]}
        existing["sources"].extend(source for source in finding["sources"]
                                   if (source.get("tool"), source.get("rule_id")) not in source_keys)
        if severity_rank.get(finding["severity"], 0) > severity_rank.get(existing["severity"], 0):
            existing["severity"] = finding["severity"]
            existing["title"] = finding["title"]
            existing["message"] = finding["message"]
            existing["description"] = finding["description"]
        existing["confidence"] = str(min(1.0, max(float(existing["confidence"]), float(finding["confidence"])) + 0.05))
    return list(groups.values())


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
