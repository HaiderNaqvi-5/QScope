"""Structured security adapter tests."""
import json

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


def test_runtime_failure_is_actionable_without_raw_secret_data():
    findings = normalize_tool_output("scan", {
        "task_id": "runtime-postman", "tool": "newman", "stage": "API_TESTING",
        "target": "http://127.0.0.1:8000", "status": "FAILED",
        "output": "POST http://127.0.0.1:8000/login failed with status 500",
    })
    assert findings[0]["severity"] == "HIGH"
    assert "127.0.0.1:8000" in findings[0]["message"]


def test_axe_violations_are_normalized():
    findings = normalize_tool_output("scan", {
        "tool": "axe", "stage": "ACCESSIBILITY", "output": '{"violations": [{"id": "button-name", "impact": "critical", "description": "Buttons must have discernible text", "nodes": [{"target": ["#save"], "failureSummary": "Fix any of the following"}]}]}'
    })
    assert findings[0]["severity"] == "CRITICAL"
    assert "#save" in findings[0]["message"]


def test_lighthouse_scores_are_normalized():
    findings = normalize_tool_output("scan", {
        "tool": "lighthouse", "stage": "PERFORMANCE", "output": '{"categories": {"performance": {"score": 0.4, "title": "Performance"}}, "audits": {}}'
    })
    assert findings[0]["title"] == "Lighthouse: performance"
    assert findings[0]["severity"] == "HIGH"


def test_newman_failed_assertion_includes_safe_request_evidence():
    findings = normalize_tool_output("scan", {
        "tool": "newman", "stage": "API_TESTING", "output": '{"run": {"executions": [{"request": {"method": "POST", "url": {"raw": "http://127.0.0.1:8000/login"}}, "response": {"code": 500, "responseTime": 42}, "assertions": [{"assertion": "status", "error": {"message": "expected 200"}}]}]}}'
    })
    assert findings[0]["title"] == "Newman: POST http://127.0.0.1:8000/login"
    assert "status 500" in findings[0]["message"]
    assert "password" not in findings[0]["message"].lower()


def test_schemathesis_failed_case_is_normalized():
    findings = normalize_tool_output("scan", {
        "tool": "schemathesis", "stage": "API_TESTING", "output": '{"results": [{"method": "GET", "path": "/users", "status": "failure", "response": {"status_code": 500}, "message": "server error"}]}'
    })
    assert findings[0]["title"] == "Schemathesis: GET /users"
    assert "status 500" in findings[0]["message"]


def test_trivy_json_is_normalized_without_secret_values():
    findings = normalize_tool_output("scan-1", {
        "tool": "trivy",
        "stage": "CONTAINER_SECURITY",
        "status": "PASSED",
        "output": json.dumps({"Results": [{
            "Target": "Dockerfile",
            "Vulnerabilities": [{
                "VulnerabilityID": "CVE-2026-0001",
                "Severity": "HIGH",
                "Title": "Example vulnerable package",
                "InstalledVersion": "1.0",
                "FixedVersion": "1.1",
            }],
        }]}),
    })
    assert len(findings) == 1
    assert findings[0]["severity"] == "HIGH"
    assert findings[0]["title"] == "Trivy: CVE-2026-0001"
    assert "CVE-2026-0001" in findings[0]["message"]


def test_osv_json_is_normalized_with_package_evidence():
    findings = normalize_tool_output("scan", {"tool": "osv-scanner", "stage": "DEPENDENCY_VULNERABILITIES",
        "status": "FAILED", "output": json.dumps({"results": [{"source": {"path": "package-lock.json"},
        "packages": [{"package": {"name": "demo", "version": "1.0"},
        "vulnerabilities": [{"id": "GHSA-test", "summary": "Test advisory"}]}]}]})})
    assert findings[0]["title"] == "GHSA-test affects demo"
    assert findings[0]["category"] == "DEPENDENCIES"
    assert findings[0]["file_path"] == "package-lock.json"


def test_lizard_complexity_csv_is_normalized():
    output = "NLOC,CCN,token,PARAM,length,location,file,function_name,long_name,start line,end line\n120,22,1,0,120,x,app.py,handler,handler(),10,130\n"
    findings = normalize_tool_output("scan", {"tool": "lizard", "stage": "CODE_QUALITY", "status": "PASSED", "output": output})
    assert findings[0]["title"] == "Complex function: handler"
    assert findings[0]["line"] == "10"


def test_jscpd_console_output_is_normalized():
    findings = normalize_tool_output("scan", {"tool": "jscpd", "stage": "CODE_QUALITY", "status": "FAILED",
        "output": "src/a.ts:10 duplicate block matches src/b.ts:20"})
    assert findings[0]["title"] == "Duplicated code block"
    assert findings[0]["file_path"] == "src/a.ts"
