"""Deterministic audit completeness and release-readiness policy."""
from __future__ import annotations

from typing import Any

INCOMPLETE_STATES = {"TOOL_ERROR", "TOOL_MISSING", "SKIPPED_DEPENDENCY", "TIMED_OUT", "ERROR"}
ACTIVE_FINDING_STATES = {"OPEN", "ACKNOWLEDGED", "FIXED_PENDING_VERIFY", "FIX_APPLIED_PENDING_VERIFICATION"}


def evaluate_release_gate(findings: list[dict[str, Any]], results: list[dict[str, Any]], *, full_audit: bool) -> dict[str, Any]:
    """Return a release decision with evidence-backed, human-readable blockers."""
    blockers: list[str] = []
    incompleteness = [
        f"{result.get('task_id', result.get('stage', 'unknown task'))}: {result.get('status')}"
        for result in results if result.get("status") in INCOMPLETE_STATES
    ]
    unresolved = [finding for finding in findings if finding.get("status", "OPEN") in ACTIVE_FINDING_STATES]
    if any(finding.get("severity") == "CRITICAL" and finding.get("category") == "SECURITY" for finding in unresolved):
        blockers.append("Unresolved CRITICAL security finding")
    if any(result.get("status") == "FAILED" and result.get("stage") in {"BUILD_TYPECHECK", "BUILD_COMPILE_TYPECHECK"} for result in results):
        blockers.append("Primary build, compile, or typecheck failed")
    if any(result.get("status") == "FAILED" and result.get("stage") in {"TESTS", "UNIT_TESTS", "INTEGRATION_TESTS"} for result in results):
        blockers.append("Required existing test suite failed")
    if any(finding.get("subcategory") == "SECRETS" and finding.get("severity") in {"CRITICAL", "HIGH"} for finding in unresolved) or any(
        result.get("status") == "FAILED" and result.get("stage") in {"SECRETS", "SECRET_SCANNING"} for result in results
    ):
        blockers.append("Confirmed secret remains in committed source or history")
    if blockers:
        decision = "NOT READY"
    elif full_audit and incompleteness:
        decision = "INCOMPLETE AUDIT"
    elif any(finding.get("severity") in {"HIGH", "MEDIUM"} for finding in unresolved) or any(
        result.get("status") in {"FAILED", "WARNING", "SKIPPED_USER"} for result in results
    ):
        decision = "READY WITH WARNINGS"
    else:
        decision = "RELEASE READY"
    return {
        "decision": decision,
        "blockers": blockers,
        "is_complete_audit": not incompleteness,
        "incomplete_reasons": incompleteness,
    }
