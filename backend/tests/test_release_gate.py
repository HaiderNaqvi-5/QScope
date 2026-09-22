from app.services.release_gate import evaluate_release_gate


def test_critical_security_is_not_ready_even_with_complete_tasks():
    gate = evaluate_release_gate(
        [{"severity": "CRITICAL", "category": "SECURITY", "status": "OPEN"}],
        [{"task_id": "sast", "status": "PASSED", "stage": "SAST"}], full_audit=True,
    )
    assert gate["decision"] == "NOT READY"
    assert "CRITICAL" in gate["blockers"][0]


def test_full_audit_tool_failure_is_explicitly_incomplete():
    gate = evaluate_release_gate([], [{"task_id": "zap", "status": "TOOL_ERROR"}], full_audit=True)
    assert gate["decision"] == "INCOMPLETE AUDIT"
    assert gate["is_complete_audit"] is False
    assert gate["incomplete_reasons"] == ["zap: TOOL_ERROR"]


def test_verified_findings_do_not_block_release():
    gate = evaluate_release_gate(
        [{"severity": "CRITICAL", "category": "SECURITY", "status": "VERIFIED_FIXED"}], [], full_audit=True
    )
    assert gate["decision"] == "RELEASE READY"


def test_nonblocking_quality_findings_yield_ready_with_warnings():
    gate = evaluate_release_gate([{"severity": "MEDIUM", "status": "OPEN"}], [], full_audit=False)
    assert gate["decision"] == "READY WITH WARNINGS"
