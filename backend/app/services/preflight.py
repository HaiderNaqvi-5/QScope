"""Tool availability and deterministic scan-plan generation."""
from __future__ import annotations

import shutil
import subprocess
from typing import Any

from app.schemas.projects import ScanTask, ToolStatus


TOOL_DEFINITIONS = (
    ("git", "Git", False, "Install Git and ensure it is on PATH."),
    ("python", "Python", True, "Install Python 3.11 or newer."),
    ("node", "Node.js", False, "Install Node.js for JavaScript/TypeScript projects."),
    ("npm", "npm", False, "Install npm with Node.js."),
    ("pytest", "pytest", False, "Install pytest in the project environment."),
    ("ruff", "Ruff", False, "Install Ruff or add it to the project environment."),
    ("semgrep", "Semgrep", False, "Install Semgrep Community Edition."),
    ("gitleaks", "Gitleaks", False, "Install Gitleaks."),
    ("osv-scanner", "OSV-Scanner", False, "Install OSV-Scanner for dependency vulnerability analysis."),
    ("schemathesis", "Schemathesis", False, "Install Schemathesis for OpenAPI API testing."),
)


def _version(executable: str) -> str | None:
    try:
        result = subprocess.run([executable, "--version"], capture_output=True, text=True, timeout=3, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return (result.stdout or result.stderr).strip().splitlines()[0][:200] or None


def inspect_tools(model: dict[str, Any]) -> list[ToolStatus]:
    languages = {item["value"] for item in model.get("languages", [])}
    relevant = {"python", "pytest", "ruff"} if "Python" in languages else set()
    if languages & {"JavaScript", "TypeScript"}:
        relevant |= {"node", "npm"}
    relevant |= {"git", "semgrep", "gitleaks", "osv-scanner"}
    if model.get("api_specs"):
        relevant.add("schemathesis")
    return [
        ToolStatus(
            id=tool_id, display_name=name, executable=tool_id,
            available=shutil.which(tool_id) is not None,
            version=_version(tool_id) if shutil.which(tool_id) else None,
            required=required and tool_id in relevant,
            guidance=None if shutil.which(tool_id) else guidance,
        )
        for tool_id, name, required, guidance in TOOL_DEFINITIONS
        if tool_id in relevant
    ]


def build_scan_plan(project_id: str, model: dict[str, Any], mode: str) -> tuple[list[ToolStatus], list[ScanTask]]:
    tools = inspect_tools(model)
    tasks = [
        ScanTask(task_id="discovery", stage="PROJECT_DISCOVERY", adapter="core", tool="qsscope", target=".", status="PASSED"),
        ScanTask(task_id="preflight", stage="PREFLIGHT", adapter="core", tool="registry", target=".", depends_on=["discovery"]),
    ]
    languages = {item["value"] for item in model.get("languages", [])}
    if "Python" in languages:
        tasks += [
            ScanTask(task_id="python-compile", stage="BUILD_TYPECHECK", adapter="python", tool="python", target=".", depends_on=["preflight"]),
            ScanTask(task_id="python-tests", stage="TESTS", adapter="python", tool="pytest", target=".", depends_on=["python-compile"]),
        ]
    if languages & {"JavaScript", "TypeScript"}:
        tasks.append(ScanTask(task_id="js-lint", stage="STATIC_ANALYSIS", adapter="javascript", tool="npm", target=".", depends_on=["preflight"]))
    tasks += [
        ScanTask(task_id="dependency-inventory", stage="DEPENDENCY_INVENTORY", adapter="core", tool="qsscope", target=".", depends_on=["preflight"]),
        ScanTask(task_id="secrets", stage="SECRETS", adapter="universal", tool="gitleaks", target=".", depends_on=["preflight"]),
        ScanTask(task_id="sast", stage="SAST", adapter="universal", tool="semgrep", target=".", depends_on=["preflight"]),
    ]
    if any(tool.id == "osv-scanner" and tool.available for tool in tools):
        tasks.append(ScanTask(task_id="dependency-audit", stage="DEPENDENCY_VULNERABILITIES", adapter="universal", tool="osv-scanner", target=".", depends_on=["dependency-inventory"]))
    if mode == "FULL" and model.get("api_specs"):
        tasks.append(ScanTask(task_id="runtime-api", stage="API_TESTING", adapter="universal", tool="schemathesis", target=".", depends_on=["preflight"], requires_runtime=True, requires_user_confirmation=True, estimated_cost="HIGH"))
    return tools, tasks
