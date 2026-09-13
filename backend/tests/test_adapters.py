"""Structured security adapter tests."""
from app.services.findings import deduplicate_findings, normalize_tool_output


def test_semgrep_output_is_normalized():
    findings = normalize_tool_output("scan", {
        "tool": "semgrep", "stage": "SAST", "output": '{"results": [{"check_id": "python.lang.security", "path": "app.py", "start": {"line": 8}, "extra": {"message": "bad input", "severity": "ERROR"}}]}'
    })
    assert findings[0]["file_path"] == "app.py"
    assert findings[0]["severity"] == "HIGH"


def test_gitleaks_never_persists_secret_value():
    findings = normalize_tool_output("scan", {
        "tool": "gitleaks", "output": '[{"RuleID": "aws-key", "Secret": "DO_NOT_STORE", "File": "config.py", "StartLine": 4}]'
    })
    assert "DO_NOT_STORE" not in findings[0]["message"]
    assert findings[0]["severity"] == "HIGH"


def test_findings_are_deduplicated():
    finding = {"fingerprint": "same", "title": "one"}
    assert deduplicate_findings([finding, {**finding, "title": "two"}]) == [finding]
