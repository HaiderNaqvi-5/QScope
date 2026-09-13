"""Normalized finding and scoring tests."""
from app.services.findings import analyze_code_hygiene, normalize_result, score_findings


def test_failed_task_normalizes_with_location():
    finding = normalize_result("scan-1", {
        "task_id": "python-tests", "stage": "TESTS", "tool": "pytest",
        "status": "FAILED", "output": "tests/test_api.py:12: assertion failed",
    })
    assert finding is not None
    assert finding["file_path"] == "tests/test_api.py"
    assert finding["line"] == "12"
    assert finding["severity"] == "MEDIUM"


def test_score_is_bounded():
    assert score_findings([{"severity": "HIGH"}]) == 80
    assert score_findings([{"severity": "CRITICAL"}, {"severity": "HIGH"}]) == 45


def test_code_hygiene_is_local_bounded_and_advisory(tmp_path):
    source = tmp_path / "app.py"
    source.write_text("print('debug')\n# TODO: remove this\n")
    findings = analyze_code_hygiene("scan-1", tmp_path)
    assert {item["severity"] for item in findings} == {"LOW"}
    assert all(item["file_path"] == "app.py" for item in findings)
    assert all("auth" not in item["message"].lower() for item in findings)
