"""Strong-correlation validation for shared-root-cause Fix Packs."""
from typing import Any


def validate_fix_pack(findings: list[Any], root_cause_id: str, confidence: float,
                      verification_scenarios: dict[str, list]) -> list[str]:
    reasons = []
    if len(findings) < 2:
        reasons.append("A Fix Pack requires at least two member findings.")
    if confidence < 0.9:
        reasons.append("Fix Pack correlation confidence must be at least 0.90.")
    correlation_keys = {getattr(item, "correlation_key", None) for item in findings}
    if correlation_keys != {root_cause_id}:
        reasons.append("Every member finding must share the proven root-cause correlation key.")
    missing = [item.id for item in findings if not verification_scenarios.get(item.id)]
    if missing:
        reasons.append("Every member finding requires at least one verification scenario: " + ", ".join(missing))
    return reasons
