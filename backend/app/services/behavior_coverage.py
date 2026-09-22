"""Map observable project behaviors to test evidence."""
from __future__ import annotations

import hashlib
from typing import Any


def coverage_from_generated(case: Any) -> dict[str, Any]:
    coverage = {"PASSED": "COVERED", "FAILED": "PARTIALLY_COVERED", "GENERATED": "UNTESTED"}.get(
        case.status, "UNKNOWN")
    criticality = "HIGH" if case.category == "LOGICAL" or case.method in {"POST", "PUT", "PATCH", "DELETE"} else "NORMAL"
    key = f"{case.category}:{case.method}:{case.endpoint}:{case.title}"
    return {"capability_key": key, "category": case.category, "title": case.title,
            "criticality": criticality, "coverage_status": coverage, "source": "GENERATED_TEST",
            "evidence": {"generated_test_id": case.id, "test_status": case.status, "endpoint": case.endpoint}}


def coverage_from_manual(case: Any) -> dict[str, Any]:
    coverage = {"PASS": "COVERED", "FAIL": "PARTIALLY_COVERED", "NOT_RUN": "UNTESTED"}.get(case.status, "UNKNOWN")
    key = f"MANUAL:{case.module}:{case.feature or ''}"
    return {"capability_key": key, "category": "MANUAL", "title": f"{case.module}: {case.feature or 'manual workflow'}",
            "criticality": "HIGH" if case.severity in {"CRITICAL", "HIGH"} else "NORMAL",
            "coverage_status": coverage, "source": "MANUAL_TEST",
            "evidence": {"manual_test_id": case.id, "test_status": case.status}}


def coverage_from_test_run(run: Any) -> dict[str, Any]:
    if run.discovered == 0:
        coverage = "UNKNOWN"
    elif run.failed:
        coverage = "PARTIALLY_COVERED"
    else:
        coverage = "COVERED"
    return {"capability_key": f"SUITE:{run.task_id or run.suite_name}", "category": "TEST_SUITE",
            "title": run.suite_name, "criticality": "NORMAL", "coverage_status": coverage,
            "source": "EXISTING_TEST_SUITE", "evidence": {"test_run_id": run.id, "discovered": run.discovered,
                                                               "passed": run.passed, "failed": run.failed}}


def coverage_fingerprint(project_id: str, capability_key: str) -> str:
    return hashlib.sha256(f"{project_id}|{capability_key}".encode()).hexdigest()
