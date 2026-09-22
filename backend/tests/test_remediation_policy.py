import hashlib

import pytest
from pydantic import ValidationError

from app.schemas.remediation import RemediationPlan
from app.services.remediation_policy import remediation_eligibility, validate_unified_patch


def plan(**overrides):
    values = {"finding_ids": ["f1"], "root_cause": "Missing range guard", "proposed_strategy": "Validate input",
              "expected_files": ["app/validator.py"], "expected_tests": ["test_range"],
              "expected_behavior_after_fix": "Invalid values return 422", "risk": "SAFE", "fix_confidence": 0.95}
    values.update(overrides)
    return RemediationPlan(**values)


def test_high_risk_changes_cannot_be_disguised_as_safe():
    with pytest.raises(ValidationError):
        plan(database_change=True)
    result = remediation_eligibility(plan(risk="HIGH_RISK", database_change=True), "AUTONOMOUS", reproduced=True)
    assert result.action == "MANUAL_REVIEW"


def test_low_fix_confidence_downgrades_autonomous_action():
    result = remediation_eligibility(plan(fix_confidence=0.4), "AUTONOMOUS", reproduced=True)
    assert result.action == "ASSISTED"
    assert result.requires_approval is True


def test_unconfirmed_runtime_defect_cannot_be_applied():
    result = remediation_eligibility(plan(), "AUTONOMOUS", reproduced=False)
    assert result.eligible is False
    assert result.action == "MANUAL_REVIEW"


def test_patch_preflight_accepts_small_local_change(tmp_path):
    source = tmp_path / "app.py"
    source.write_text("value = 1\n")
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    patch = "--- a/app.py\n+++ b/app.py\n@@ -1 +1 @@\n-value = 1\n+value = 2\n"
    result = validate_unified_patch(patch, tmp_path, expected_hashes={"app.py": digest})
    assert result.accepted is True
    assert result.files == ["app.py"]


@pytest.mark.parametrize("target", ["../outside.py", ".env", "alembic/versions/999.py", "package-lock.json"])
def test_patch_preflight_rejects_forbidden_targets(tmp_path, target):
    patch = f"--- a/{target}\n+++ b/{target}\n@@ -1 +1 @@\n-old\n+new\n"
    result = validate_unified_patch(patch, tmp_path)
    assert result.outcome == "PATCH_REJECTED"


def test_patch_preflight_rejects_stale_context_and_added_secret(tmp_path):
    source = tmp_path / "app.py"
    source.write_text("changed by user\n")
    patch = "--- a/app.py\n+++ b/app.py\n@@ -1 +1 @@\n-old\n+api_key = 'abcdefghijklmnop'\n"
    result = validate_unified_patch(patch, tmp_path, expected_hashes={"app.py": "stale"})
    assert result.accepted is False
    assert len(result.reasons) == 2
