"""Scoped patch checkpoint, application, and rollback primitives."""
from __future__ import annotations

import base64
import hashlib
import subprocess
import asyncio
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.services.remediation_policy import validate_unified_patch

ALLOWED_VERIFICATION_EXECUTABLES = {"python", "python3", "pytest", "npm", "pnpm", "yarn", "node", "go", "cargo", "mvn", "gradle", "php", "composer", "dotnet", "ruff", "mypy"}
FORBIDDEN_VERIFICATION_ARGUMENTS = {"install", "add", "remove", "publish", "deploy", "--fix", "-c", "--eval", "-e"}


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def create_checkpoint(project_root: Path, attempt_id: str, files: list[str],
                      verification_plan: list[str]) -> dict[str, Any]:
    root = project_root.resolve()
    snapshots: dict[str, dict[str, Any]] = {}
    for relative in files:
        path = (root / relative).resolve()
        if path != root and root not in path.parents:
            raise ValueError(f"Checkpoint path escapes project: {relative}")
        content = path.read_bytes() if path.is_file() else b""
        snapshots[relative] = {
            "existed": path.is_file(), "sha256": _sha256(content) if path.is_file() else "MISSING",
            "content_base64": base64.b64encode(content).decode("ascii"),
        }
    git_head = None
    dirty_paths: list[str] = []
    try:
        head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, capture_output=True,
                              text=True, timeout=3, check=False)
        status = subprocess.run(["git", "status", "--porcelain=v1"], cwd=root, capture_output=True,
                                text=True, timeout=3, check=False)
        if head.returncode == 0:
            git_head = head.stdout.strip()
        if status.returncode == 0:
            dirty_paths = [line[3:] for line in status.stdout.splitlines() if len(line) > 3]
    except (OSError, subprocess.TimeoutExpired):
        pass
    return {"attempt_id": attempt_id, "created_at": datetime.now(timezone.utc).isoformat(),
            "files": snapshots, "git_head": git_head, "dirty_paths": dirty_paths,
            "verification_plan": verification_plan}


def apply_patch(project_root: Path, patch: str, checkpoint: dict[str, Any]) -> list[str]:
    expected = {name: snapshot["sha256"] for name, snapshot in checkpoint["files"].items()}
    validation = validate_unified_patch(patch, project_root, expected_hashes=expected)
    if not validation.accepted:
        raise ValueError("PATCH_REJECTED: " + "; ".join(validation.reasons))
    root = project_root.resolve()
    checked = subprocess.run(["git", "apply", "--check", "--whitespace=error-all", "-"], cwd=root,
                             input=patch, capture_output=True, text=True, timeout=10, check=False)
    if checked.returncode != 0:
        raise ValueError("PATCH_REJECTED: " + (checked.stderr.strip() or "git apply check failed"))
    applied = subprocess.run(["git", "apply", "--whitespace=error-all", "-"], cwd=root,
                             input=patch, capture_output=True, text=True, timeout=10, check=False)
    if applied.returncode != 0:
        raise RuntimeError(applied.stderr.strip() or "Patch application failed")
    return validation.files


def rollback_checkpoint(project_root: Path, checkpoint: dict[str, Any]) -> dict[str, str]:
    root = project_root.resolve()
    restored: dict[str, str] = {}
    for relative, snapshot in checkpoint["files"].items():
        path = (root / relative).resolve()
        if path != root and root not in path.parents:
            raise ValueError(f"Rollback path escapes project: {relative}")
        content = base64.b64decode(snapshot["content_base64"])
        if snapshot["existed"]:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
            restored[relative] = _sha256(path.read_bytes())
        elif path.exists():
            path.unlink()
            restored[relative] = "REMOVED"
        expected = snapshot["sha256"] if snapshot["existed"] else "REMOVED"
        if restored.get(relative, "REMOVED") != expected:
            raise RuntimeError(f"Rollback verification failed for {relative}")
    return restored


async def run_verification_check(project_root: Path, check: dict[str, Any]) -> dict[str, Any]:
    argv = check["argv"]
    if Path(argv[0]).name not in ALLOWED_VERIFICATION_EXECUTABLES:
        raise ValueError(f"Verification executable is not allowed: {argv[0]}")
    if any(argument.lower() in FORBIDDEN_VERIFICATION_ARGUMENTS for argument in argv[1:]):
        raise ValueError("Verification command contains a mutation-capable argument")
    root = project_root.resolve()
    cwd = (root / check.get("working_directory", ".")).resolve()
    if (cwd != root and root not in cwd.parents) or not cwd.is_dir():
        raise ValueError("Verification working directory escapes the project")
    process = await asyncio.create_subprocess_exec(*argv, cwd=cwd, stdout=asyncio.subprocess.PIPE,
                                                   stderr=asyncio.subprocess.STDOUT, start_new_session=True)
    try:
        output, _ = await asyncio.wait_for(process.communicate(), timeout=check.get("timeout_seconds", 60))
    except asyncio.TimeoutError:
        process.kill()
        await process.wait()
        return {"name": check["name"], "status": "TIMED_OUT", "exit_code": None, "output": "Verification timed out."}
    return {"name": check["name"], "status": "PASSED" if process.returncode == 0 else "FAILED",
            "exit_code": process.returncode, "output": output.decode("utf-8", errors="replace")[-20_000:]}
