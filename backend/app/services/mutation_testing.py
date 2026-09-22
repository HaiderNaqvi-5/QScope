"""Isolated, bounded mutation-test execution for supported ecosystems."""
from __future__ import annotations

import asyncio
import hashlib
from pathlib import Path
import re
import shutil
import tempfile
from typing import Any


_IGNORED = {".git", ".qsscope", ".venv", "venv", "node_modules", "dist", "build", ".next"}


def select_mutation_engine(root: Path, requested: str = "AUTO") -> tuple[str | None, list[str] | None]:
    has_python = (root / "pyproject.toml").is_file() or (root / "requirements.txt").is_file()
    has_node = (root / "package.json").is_file()
    if requested in {"AUTO", "MUTMUT"} and has_python:
        executable = shutil.which("mutmut")
        return ("MUTMUT", [executable, "run"]) if executable else ("MUTMUT", None)
    if requested in {"AUTO", "STRYKER"} and has_node:
        executable = shutil.which("npx")
        return ("STRYKER", [executable, "stryker", "run"]) if executable else ("STRYKER", None)
    return None, None


def parse_mutation_output(output: str) -> dict[str, Any]:
    """Parse stable summary terms without retaining source or mutant diffs."""
    counts: dict[str, int] = {}
    for label in ("killed", "survived", "timeout", "suspicious", "skipped"):
        matches = re.findall(rf"(?i)\b{label}\D{{0,12}}(\d+)", output)
        counts[label] = int(matches[-1]) if matches else 0
    killed, survived = counts["killed"], counts["survived"]
    total = killed + survived + counts["timeout"] + counts["suspicious"]
    score = round(killed * 100 / total, 2) if total else None
    return {"killed": killed, "survived": survived, "total": total,
            "mutation_score": score, "summary_counts": counts}


async def run_mutation_analysis(root: Path, requested: str, timeout_seconds: int) -> dict[str, Any]:
    engine, command = select_mutation_engine(root, requested)
    if engine is None:
        return {"engine": None, "status": "NOT_APPLICABLE", "message": "No supported mutation adapter applies."}
    if command is None:
        return {"engine": engine, "status": "TOOL_MISSING",
                "message": f"{engine} applies but its local executable is unavailable."}
    with tempfile.TemporaryDirectory(prefix="qsscope-mutation-") as temp_dir:
        workspace = Path(temp_dir) / "project"
        shutil.copytree(root, workspace, ignore=shutil.ignore_patterns(*_IGNORED), symlinks=False)
        process = await asyncio.create_subprocess_exec(
            *command, cwd=workspace, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout_seconds)
        except asyncio.TimeoutError:
            process.kill()
            await process.wait()
            return {"engine": engine, "status": "TIMED_OUT",
                    "message": f"Mutation analysis exceeded the {timeout_seconds}s budget."}
    output = (stdout + b"\n" + stderr).decode("utf-8", errors="replace")
    parsed = parse_mutation_output(output)
    status = "COMPLETED" if process.returncode == 0 or parsed["total"] else "FAILED"
    return {"engine": engine, "status": status, **parsed,
            "evidence": {"exit_code": process.returncode, "isolated_workspace": True,
                         "output_sha256": hashlib.sha256(output.encode()).hexdigest()},
            "message": ("Surviving mutations indicate weak assertions or test strength; they are not "
                        "automatically confirmed production defects.")}
