"""Deterministic safety policy; the LLM never decides whether code may be written."""
from __future__ import annotations

import re
from pathlib import Path, PurePosixPath

from app.schemas.remediation import PatchPreflightResult, RemediationEligibility, RemediationPlan

MAX_FILES = 3
MAX_CHANGED_LINES = 120
AUTONOMOUS_CONFIDENCE = 0.85
FORBIDDEN_NAMES = {".env", ".env.local", ".env.production", "credentials", "id_rsa", "id_ed25519"}
FORBIDDEN_PARTS = {"migrations", "alembic", ".qsscope", ".git", "terraform", "infrastructure"}
LOCK_FILES = {"package-lock.json", "pnpm-lock.yaml", "yarn.lock", "poetry.lock", "uv.lock", "composer.lock", "cargo.lock"}


def remediation_eligibility(plan: RemediationPlan, mode: str, *, reproduced: bool,
                            deterministic_static_evidence: bool = False) -> RemediationEligibility:
    reasons: list[str] = []
    if not reproduced and not deterministic_static_evidence:
        reasons.append("The defect is not reproducibly or independently confirmed.")
    if plan.risk in {"HIGH_RISK", "AMBIGUOUS"}:
        reasons.append(f"{plan.risk} remediation is review-only.")
    if mode == "SUGGEST_ONLY":
        return RemediationEligibility(eligible=not reasons, requires_approval=False, action="SUGGEST", reasons=reasons)
    if reasons:
        return RemediationEligibility(eligible=False, requires_approval=True, action="MANUAL_REVIEW", reasons=reasons)
    if mode == "AUTONOMOUS" and plan.fix_confidence >= AUTONOMOUS_CONFIDENCE:
        return RemediationEligibility(eligible=True, requires_approval=False, action="AUTO_APPLY")
    if plan.fix_confidence < AUTONOMOUS_CONFIDENCE:
        reasons.append("Fix confidence is below the autonomous threshold.")
    return RemediationEligibility(eligible=True, requires_approval=True, action="ASSISTED", reasons=reasons)


def _unsafe_path(path_text: str, root: Path) -> str | None:
    normalized = normalize_patch_path(path_text)
    path = PurePosixPath(normalized)
    if path.is_absolute() or ".." in path.parts:
        return "Patch path escapes the selected project root."
    lowered = {part.lower() for part in path.parts}
    name = path.name.lower()
    if name in FORBIDDEN_NAMES or name.startswith(".env") or lowered & FORBIDDEN_PARTS:
        return "Patch touches a forbidden credential, migration, infrastructure, Git, or QSScope path."
    if name in LOCK_FILES or name in {"package.json", "pyproject.toml", "requirements.txt", "go.mod", "cargo.toml"}:
        return "Dependency manifests and lockfiles cannot be changed automatically."
    candidate = (root / normalized).resolve()
    resolved_root = root.resolve()
    if candidate != resolved_root and resolved_root not in candidate.parents:
        return "Patch path escapes the selected project root."
    return None


def normalize_patch_path(path_text: str) -> str:
    return path_text.removeprefix("a/").removeprefix("b/")


def validate_unified_patch(patch: str, project_root: Path, *, expected_hashes: dict[str, str] | None = None) -> PatchPreflightResult:
    reasons: list[str] = []
    files = re.findall(r"^\+\+\+\s+(.+)$", patch, flags=re.MULTILINE)
    files = [item.strip().split("\t", 1)[0] for item in files if item.strip() != "/dev/null"]
    changed_lines = sum(1 for line in patch.splitlines() if line.startswith(("+", "-")) and not line.startswith(("+++", "---")))
    if not patch.startswith("--- ") or not files or "@@" not in patch:
        reasons.append("Patch is not a parseable unified diff.")
    if len(set(files)) > MAX_FILES:
        reasons.append(f"Patch modifies more than {MAX_FILES} files.")
    if changed_lines > MAX_CHANGED_LINES:
        reasons.append(f"Patch changes more than {MAX_CHANGED_LINES} lines.")
    for file_name in files:
        unsafe = _unsafe_path(file_name, project_root)
        if unsafe and unsafe not in reasons:
            reasons.append(unsafe)
    added = "\n".join(line[1:] for line in patch.splitlines() if line.startswith("+") and not line.startswith("+++"))
    if re.search(r"(?i)(api[_-]?key|secret|password|token)\s*[:=]\s*['\"]?[A-Za-z0-9_\-/]{12,}", added):
        reasons.append("Added lines appear to contain a credential or secret.")
    if expected_hashes:
        import hashlib
        for relative, expected in expected_hashes.items():
            path = (project_root / relative).resolve()
            actual = hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else "MISSING"
            if actual != expected:
                reasons.append(f"File changed since context capture: {relative}")
    normalized_files = sorted({normalize_patch_path(item) for item in files})
    return PatchPreflightResult(accepted=not reasons, outcome="READY" if not reasons else "PATCH_REJECTED",
                                files=normalized_files, changed_lines=changed_lines, reasons=reasons)
