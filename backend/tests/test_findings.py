"""Normalized finding and scoring tests."""
from app.services.findings import analyze_code_hygiene, correlate_findings, normalize_result, score_findings


def test_failed_task_normalizes_with_location():
    finding = normalize_result("scan-1", {
        "task_id": "python-tests", "stage": "TESTS", "tool": "pytest",
        "status": "FAILED", "output": "tests/test_api.py:12: assertion failed",
    })
    assert finding is not None
    assert finding["file_path"] == "tests/test_api.py"
    assert finding["line"] == "12"
    assert finding["severity"] == "MEDIUM"
    assert finding["category"] == "TESTS"
    assert finding["confidence"] == "0.98"
    assert finding["sources"][0]["tool"] == "pytest"


def test_score_is_bounded():
    assert score_findings([{"severity": "HIGH"}]) == 88
    assert score_findings([{"severity": "CRITICAL", "fingerprint": "one"},
                           {"severity": "HIGH", "fingerprint": "two"}]) == 63


def test_locked_release_caps_are_applied():
    critical_security = {"severity": "CRITICAL", "category": "SECURITY", "fingerprint": "critical"}
    assert score_findings([critical_security]) == 59
    assert score_findings([], [{"stage": "BUILD_TYPECHECK", "status": "FAILED"}]) == 39
    assert score_findings([], [{"stage": "TESTS", "status": "FAILED"}]) == 69
    assert score_findings([], [{"stage": "SECRETS", "status": "FAILED"}]) == 49


def test_duplicate_fingerprint_is_penalized_once():
    finding = {"severity": "MEDIUM", "category": "SECURITY", "fingerprint": "same"}
    assert score_findings([finding, finding]) == 95


def test_same_location_findings_are_correlated_and_sources_retained():
    first = normalize_result("scan", {"task_id": "sast", "stage": "SAST", "tool": "semgrep",
        "status": "FAILED", "output": "app.py:9: injection"})
    second = normalize_result("scan", {"task_id": "sast-alt", "stage": "SAST", "tool": "trivy",
        "status": "FAILED", "output": "app.py:9: unsafe input"})
    correlated = correlate_findings([first, second])
    assert len(correlated) == 1
    assert {source["tool"] for source in correlated[0]["sources"]} == {"semgrep", "trivy"}
    assert float(correlated[0]["confidence"]) > 0.85


def test_code_hygiene_is_local_bounded_and_advisory(tmp_path):
    source = tmp_path / "app.py"
    source.write_text("print('debug')\n# TODO: remove this\n")
    findings = analyze_code_hygiene("scan-1", tmp_path)
    assert {item["severity"] for item in findings} == {"LOW"}
    assert all(item["file_path"] == "app.py" for item in findings)
    assert all("auth" not in item["message"].lower() for item in findings)
