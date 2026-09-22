"""Tool availability and deterministic scan-plan generation."""
from __future__ import annotations

import shutil
import subprocess
import re
from pathlib import Path
from typing import Any

from app.schemas.projects import ScanTask, ToolStatus
from app.tools.capability import Availability, ToolDefinition
from app.tools.registry import TOOL_REGISTRY


FULL_AUDIT_STAGES: tuple[tuple[str, str], ...] = (
    ("PROJECT_DISCOVERY", "Project Discovery"),
    ("STACK_SERVICE_RUNTIME_DETECTION", "Stack, Service, Role, Schema & Runtime Detection"),
    ("DEPENDENCY_INVENTORY_SBOM", "Dependency Inventory + SBOM"),
    ("TOOL_RUNTIME_PREFLIGHT", "Tool / Runtime Preflight"),
    ("BUILD_COMPILE_TYPECHECK", "Build / Compile / Typecheck"),
    ("STATIC_CODE_QUALITY", "Static Code Quality"),
    ("COMPLEXITY_DUPLICATION_UNUSED", "Complexity + Duplication + Dead/Unused Code"),
    ("SAST", "Static Application Security Testing"),
    ("SECRET_SCANNING", "Secret Scanning"),
    ("DEPENDENCY_SECURITY", "Dependency Vulnerabilities / Licenses / Deprecations"),
    ("UNIT_TESTS", "Existing Unit Tests"),
    ("INTEGRATION_TESTS", "Existing Integration Tests"),
    ("BEHAVIOR_COVERAGE", "Coverage + Behavior/Test-Gap Mapping"),
    ("MUTATION_TESTING", "Optional Mutation / Test-Strength Analysis"),
    ("MANAGED_RUNTIME", "Start QSScope-Managed Local Runtime Targets"),
    ("CONTRACT_TESTING", "API Discovery + Frontend↔Backend Contract Testing"),
    ("STANDARD_API_TESTING", "Standard API / Newman Testing"),
    ("LOGICAL_TESTING", "Logical / Business-Rule / State-Transition Testing"),
    ("EDGE_PROPERTY_TESTING", "Edge-Case / Boundary / Property-Based Testing"),
    ("DYNAMIC_SECURITY", "Dynamic Security + Auth/AuthZ + IDOR + DAST Testing"),
    ("DATA_INTEGRITY", "Data-Integrity Testing"),
    ("CONCURRENCY_TESTING", "Limited Concurrency / Race-Condition Testing"),
    ("BROWSER_FUNCTIONAL", "Browser Functional Testing"),
    ("RESPONSIVE_VISUAL", "Responsive / Visual Testing"),
    ("ACCESSIBILITY", "Accessibility Testing"),
    ("WEB_PERFORMANCE", "Lighthouse / Web Performance"),
    ("LOAD_LATENCY", "Load / Latency Testing"),
    ("RESILIENCE", "Resilience / Controlled Failure Testing"),
    ("REGRESSION", "Regression Comparison"),
    ("CODE_HYGIENE", "AI-Slop / Code-Hygiene Heuristics"),
    ("GROQ_REVIEW_CORRELATION", "Groq Deep Review + Finding Correlation"),
    ("REMEDIATION_CLASSIFICATION", "Remediation Eligibility, Root-Cause & Risk Classification"),
    ("AUTONOMOUS_REMEDIATION", "Automated Remediation & Verification Loop"),
    ("TARGETED_RETEST", "Targeted Re-test + Impacted Regression Safety Check"),
    ("FINAL_SCORING", "Final Scoring + Release Readiness Recalculation"),
    ("REPORT_READINESS", "Report Readiness + DOCX/PDF Evidence Assembly"),
)

STAGE_ALIASES = {
    "PREFLIGHT": "TOOL_RUNTIME_PREFLIGHT", "DEPENDENCY_INVENTORY": "DEPENDENCY_INVENTORY_SBOM",
    "SBOM": "DEPENDENCY_INVENTORY_SBOM", "BUILD_TYPECHECK": "BUILD_COMPILE_TYPECHECK",
    "STATIC_ANALYSIS": "STATIC_CODE_QUALITY", "CODE_QUALITY": "COMPLEXITY_DUPLICATION_UNUSED",
    "SECRETS": "SECRET_SCANNING", "DEPENDENCY_VULNERABILITIES": "DEPENDENCY_SECURITY",
    "TESTS": "UNIT_TESTS", "API_TESTING": "STANDARD_API_TESTING",
    "GRAPHQL_TESTING": "EDGE_PROPERTY_TESTING", "DAST": "DYNAMIC_SECURITY",
    "PERFORMANCE": "WEB_PERFORMANCE", "LOAD_TESTING": "LOAD_LATENCY",
}

QUICK_SCAN_STAGES = tuple(stage for stage, _ in FULL_AUDIT_STAGES if stage in {
    "PROJECT_DISCOVERY", "STACK_SERVICE_RUNTIME_DETECTION", "DEPENDENCY_INVENTORY_SBOM",
    "TOOL_RUNTIME_PREFLIGHT", "BUILD_COMPILE_TYPECHECK", "STATIC_CODE_QUALITY",
    "COMPLEXITY_DUPLICATION_UNUSED", "SAST", "SECRET_SCANNING", "DEPENDENCY_SECURITY",
    "UNIT_TESTS", "INTEGRATION_TESTS", "CODE_HYGIENE", "FINAL_SCORING", "REPORT_READINESS",
})
STANDARD_SCAN_STAGES = tuple(stage for stage, _ in FULL_AUDIT_STAGES if stage in set(QUICK_SCAN_STAGES) | {
    "MANAGED_RUNTIME", "CONTRACT_TESTING", "STANDARD_API_TESTING", "LOGICAL_TESTING",
    "EDGE_PROPERTY_TESTING", "BROWSER_FUNCTIONAL", "RESPONSIVE_VISUAL", "ACCESSIBILITY",
    "WEB_PERFORMANCE",
})


def _version(tool: ToolDefinition) -> tuple[Availability, str | None]:
    try:
        result = subprocess.run([tool.executable, *tool.version_args], capture_output=True, text=True, timeout=3, check=False)
    except subprocess.TimeoutExpired:
        return Availability.ERROR, None
    except OSError:
        # The executable was resolved immediately before invocation. A launch race or
        # test double can prevent version probing; retain executable readiness while
        # exposing the unknown version instead of falsely reporting it absent.
        return Availability.READY, None
    output = (result.stdout or result.stderr).strip().splitlines()
    if result.returncode != 0 or not output:
        return Availability.ERROR, output[0][:200] if output else None
    return Availability.READY, output[0][:200]


def _relevant_tool_ids(model: dict[str, Any]) -> set[str]:
    languages = {item["value"] for item in model.get("languages", [])}
    relevant = {"git", "semgrep", "gitleaks", "osv-scanner", "syft", "jscpd", "lizard"}
    ecosystem_tools = {
        "Python": {"python", "pytest", "ruff", "mypy"},
        "JavaScript": {"node", "npm", "eslint", "knip"}, "TypeScript": {"node", "npm", "eslint", "tsc", "knip"},
        "Java": {"mvn", "gradle"}, "PHP": {"php", "composer", "phpstan", "psalm"},
        "Go": {"go", "staticcheck", "govulncheck"}, "C#": {"dotnet"}, "Rust": {"cargo", "cargo-audit"},
    }
    for language in languages:
        relevant |= ecosystem_tools.get(language, set())
    feature_tools = (("docker", "trivy"), ("api_specs", "schemathesis"), ("graphql_specs", "schemathesis"),
                     ("postman_collections", "newman"), ("browser_tests", "playwright"),
                     ("accessibility_tests", "axe"), ("performance_tests", "lighthouse"),
                     ("security_tests", "zap"))
    for field, tool_id in feature_tools:
        value = model.get(field)
        if (isinstance(value, dict) and value.get("detected")) or (not isinstance(value, dict) and value):
            relevant.add(tool_id)
    if model.get("frontend_targets"):
        relevant.add("playwright")
    if model.get("load_tests"):
        relevant |= {"k6", "jmeter"}
    return relevant


def inspect_tools(model: dict[str, Any]) -> list[ToolStatus]:
    statuses: list[ToolStatus] = []
    for tool_id in sorted(_relevant_tool_ids(model)):
        tool = TOOL_REGISTRY[tool_id]
        required = tool.required
        if shutil.which(tool.executable) is None:
            state = Availability.MISSING if required else Availability.OPTIONAL_NOT_INSTALLED
            version = None
        else:
            state, version = _version(tool)
        statuses.append(ToolStatus(id=tool.id, display_name=tool.display_name, executable=tool.executable,
            available=state == Availability.READY, status=state, version=version, required=required,
            guidance=None if state == Availability.READY else tool.install_guidance,
            reason=f"Provides {', '.join(tool.categories)} coverage", categories=list(tool.categories),
            adapter=tool.adapter, license=tool.license, output_formats=list(tool.output_formats)))
    return statuses


def build_scan_plan(project_id: str, model: dict[str, Any], mode: str) -> tuple[list[ToolStatus], list[ScanTask]]:
    tools = inspect_tools(model)
    tasks = [
        ScanTask(task_id="discovery", stage="PROJECT_DISCOVERY", adapter="core", tool="qsscope", target="."),
        ScanTask(task_id="preflight", stage="PREFLIGHT", adapter="core", tool="registry", target=".", depends_on=["discovery"]),
    ]
    languages = {item["value"] for item in model.get("languages", [])}
    if "Python" in languages:
        tasks.append(ScanTask(task_id="python-compile", stage="BUILD_TYPECHECK", adapter="python", tool="python", target=".", depends_on=["preflight"]))
        if mode in {"STANDARD", "FULL"}:
            tasks.extend([
                ScanTask(task_id="python-ruff", stage="STATIC_ANALYSIS", adapter="python", tool="ruff", target=".", depends_on=["python-compile"]),
                ScanTask(task_id="python-mypy", stage="BUILD_TYPECHECK", adapter="python", tool="mypy", target=".", depends_on=["python-compile"]),
            ])
        if any("pytest" in item.get("value", "").lower() for item in model.get("test_suites", [])):
            tasks.append(ScanTask(task_id="python-tests", stage="TESTS", adapter="python", tool="pytest", target=".", depends_on=["python-compile"]))
    if languages & {"JavaScript", "TypeScript"}:
        tasks += [
            ScanTask(task_id="js-build", stage="BUILD_TYPECHECK", adapter="javascript", tool="npm", target=".", depends_on=["preflight"]),
            ScanTask(task_id="js-lint", stage="STATIC_ANALYSIS", adapter="javascript", tool="eslint", target=".", depends_on=["js-build"]),
        ]
        if "TypeScript" in languages:
            tasks.append(ScanTask(task_id="js-typecheck", stage="BUILD_TYPECHECK", adapter="javascript", tool="tsc", target=".", depends_on=["js-build"]))
        if mode in {"STANDARD", "FULL"}:
            tasks.append(ScanTask(task_id="js-knip", stage="CODE_QUALITY", adapter="javascript", tool="knip", target=".", depends_on=["js-build"]))
        if any("javascript" in item.get("value", "").lower() or "jest" in item.get("value", "").lower()
               or "vitest" in item.get("value", "").lower() for item in model.get("test_suites", [])):
            tasks.append(ScanTask(task_id="js-tests", stage="TESTS", adapter="javascript", tool="npm", target=".", depends_on=["js-build"]))
    native_tasks = {
        "Java": [("java-build", "BUILD_TYPECHECK", "java", "mvn"), ("java-tests", "TESTS", "java", "mvn")],
        "PHP": [("php-build", "BUILD_TYPECHECK", "php", "composer"), ("php-tests", "TESTS", "php", "php")],
        "Go": [("go-vet", "BUILD_TYPECHECK", "go", "go"), ("go-tests", "TESTS", "go", "go")],
        "C#": [("dotnet-build", "BUILD_TYPECHECK", "dotnet", "dotnet"), ("dotnet-tests", "TESTS", "dotnet", "dotnet")],
        "Rust": [("rust-check", "BUILD_TYPECHECK", "rust", "cargo"), ("rust-clippy", "STATIC_ANALYSIS", "rust", "cargo"), ("rust-tests", "TESTS", "rust", "cargo")],
    }
    for language, definitions in native_tasks.items():
        if language in languages:
            for task_id, stage, adapter, tool in definitions:
                if language == "Java" and not model.get("manifest_evidence", {}).get("java", [""])[0].endswith("pom.xml"):
                    tool = "gradle"
                tasks.append(ScanTask(task_id=task_id, stage=stage, adapter=adapter, tool=tool,
                                      target=".", depends_on=["preflight"]))
    if "Go" in languages and mode == "FULL":
        tasks.extend([ScanTask(task_id="go-staticcheck", stage="STATIC_ANALYSIS", adapter="go", tool="staticcheck", target=".", depends_on=["go-vet"]),
                      ScanTask(task_id="go-vuln", stage="DEPENDENCY_VULNERABILITIES", adapter="go", tool="govulncheck", target=".", depends_on=["go-vet"])])
    if "Rust" in languages and mode == "FULL":
        tasks.append(ScanTask(task_id="rust-audit", stage="DEPENDENCY_VULNERABILITIES", adapter="rust", tool="cargo-audit", target=".", depends_on=["rust-check"]))
    tasks += [
        ScanTask(task_id="dependency-inventory", stage="DEPENDENCY_INVENTORY", adapter="core", tool="qsscope", target=".", depends_on=["preflight"]),
        ScanTask(task_id="code-hygiene", stage="CODE_HYGIENE", adapter="qsscope", tool="qsscope", target=".", depends_on=["preflight"], estimated_cost="LOW"),
        ScanTask(task_id="secrets", stage="SECRETS", adapter="universal", tool="gitleaks", target=".", depends_on=["preflight"]),
        ScanTask(task_id="sast", stage="SAST", adapter="universal", tool="semgrep", target=".", depends_on=["preflight"]),
    ]
    if model.get("dependencies") or model.get("manifest_evidence"):
        tasks.append(ScanTask(task_id="dependency-audit", stage="DEPENDENCY_VULNERABILITIES", adapter="universal", tool="osv-scanner", target=".", depends_on=["dependency-inventory"]))
    if mode == "FULL":
        tasks.append(ScanTask(task_id="sbom", stage="SBOM", adapter="universal", tool="syft", target=".", depends_on=["dependency-inventory"], estimated_cost="MEDIUM"))
    if mode in {"STANDARD", "FULL"}:
        tasks.extend([
            ScanTask(task_id="complexity", stage="CODE_QUALITY", adapter="universal", tool="lizard", target=".", depends_on=["preflight"], estimated_cost="MEDIUM"),
            ScanTask(task_id="duplication", stage="CODE_QUALITY", adapter="universal", tool="jscpd", target=".", depends_on=["preflight"], estimated_cost="MEDIUM"),
        ])
    if model.get("docker", {}).get("detected"):
        tasks.append(ScanTask(task_id="trivy-filesystem", stage="CONTAINER_SECURITY", adapter="universal", tool="trivy", target=".", depends_on=["preflight"], estimated_cost="MEDIUM"))
    if mode in {"STANDARD", "FULL"} and model.get("api_specs"):
        runtime_targets = model.get("runtime_targets", [])
        target = runtime_targets[0].get("base_url", "unconfigured") if runtime_targets else "unconfigured"
        tasks.append(ScanTask(task_id="runtime-api", stage="API_TESTING", adapter="universal", tool="schemathesis", target=target, depends_on=["preflight"], requires_runtime=True, requires_user_confirmation=True, estimated_cost="HIGH"))
        if model.get("frontend_targets"):
            tasks.append(ScanTask(task_id="contract-analysis", stage="CONTRACT_TESTING", adapter="universal",
                                  tool="qsscope", target=".", depends_on=["preflight"], estimated_cost="LOW"))
    if mode == "FULL" and model.get("graphql_specs"):
        runtime_targets = model.get("runtime_targets", [])
        target = runtime_targets[0].get("base_url", "unconfigured") if runtime_targets else "unconfigured"
        tasks.append(ScanTask(task_id="runtime-graphql", stage="GRAPHQL_TESTING", adapter="schemathesis", tool="schemathesis", target=target, depends_on=["preflight"], requires_runtime=True, requires_user_confirmation=True, estimated_cost="HIGH"))
    if mode in {"STANDARD", "FULL"} and model.get("postman_collections"):
        runtime_targets = model.get("runtime_targets", [])
        target = runtime_targets[0].get("base_url", "unconfigured") if runtime_targets else "unconfigured"
        tasks.append(ScanTask(task_id="runtime-postman", stage="API_TESTING", adapter="newman", tool="newman", target=target, depends_on=["preflight"], requires_runtime=True, requires_user_confirmation=True, estimated_cost="HIGH"))
    if mode in {"STANDARD", "FULL"} and (model.get("browser_tests") or model.get("frontend_targets")):
        runtime_targets = model.get("runtime_targets", [])
        target = runtime_targets[0].get("base_url", "unconfigured") if runtime_targets else "unconfigured"
        tasks.append(ScanTask(task_id="browser-functional", stage="BROWSER_FUNCTIONAL", adapter="playwright", tool="playwright", target=target, depends_on=["preflight"], requires_runtime=True, requires_user_confirmation=True, estimated_cost="HIGH"))
    if mode in {"STANDARD", "FULL"} and model.get("accessibility_tests"):
        runtime_targets = model.get("runtime_targets", [])
        target = runtime_targets[0].get("base_url", "unconfigured") if runtime_targets else "unconfigured"
        tasks.append(ScanTask(task_id="browser-accessibility", stage="ACCESSIBILITY", adapter="axe", tool="axe", target=target, depends_on=["browser-functional"], requires_runtime=True, requires_user_confirmation=True, estimated_cost="MEDIUM"))
    if mode in {"STANDARD", "FULL"} and model.get("performance_tests"):
        runtime_targets = model.get("runtime_targets", [])
        target = runtime_targets[0].get("base_url", "unconfigured") if runtime_targets else "unconfigured"
        tasks.append(ScanTask(task_id="browser-performance", stage="PERFORMANCE", adapter="lighthouse", tool="lighthouse", target=target, depends_on=["browser-functional"], requires_runtime=True, requires_user_confirmation=True, estimated_cost="MEDIUM"))
    if mode == "FULL" and model.get("security_tests"):
        runtime_targets = model.get("runtime_targets", [])
        target = runtime_targets[0].get("base_url", "unconfigured") if runtime_targets else "unconfigured"
        tasks.append(ScanTask(task_id="runtime-zap", stage="DAST", adapter="zap", tool="zap-baseline.py", target=target, depends_on=["preflight"], requires_runtime=True, requires_user_confirmation=True, estimated_cost="HIGH"))
    if mode == "FULL" and model.get("load_tests"):
        runtime_targets = model.get("runtime_targets", [])
        target = runtime_targets[0].get("base_url", "unconfigured") if runtime_targets else "unconfigured"
        load_tool = "jmeter" if any(item["value"] == "JMeter plan" for item in model["load_tests"]) else "k6"
        task_id = "runtime-jmeter" if load_tool == "jmeter" else "runtime-k6"
        tasks.append(ScanTask(task_id=task_id, stage="LOAD_TESTING", adapter=load_tool, tool=load_tool, target=target, depends_on=["preflight"], requires_runtime=True, requires_user_confirmation=True, estimated_cost="HIGH"))
    elif mode == "FULL" and model.get("backend_targets"):
        runtime_targets = model.get("runtime_targets", [])
        target = runtime_targets[0].get("base_url", "unconfigured") if runtime_targets else "unconfigured"
        tasks.append(ScanTask(task_id="runtime-qsscope-load", stage="LOAD_TESTING", adapter="universal",
                              tool="python", target=target, depends_on=["preflight"], requires_runtime=True,
                              requires_user_confirmation=True, estimated_cost="HIGH"))
    # A monorepo may contain multiple independently executable workspaces. Expand
    # ecosystem tasks so each manifest root is checked in its own working directory,
    # while keeping the historical task id for the root/first workspace.
    evidence_by_adapter = model.get("manifest_evidence", {})
    expanded: list[ScanTask] = []
    for adapter in ("python", "javascript", "java", "php", "go", "dotnet", "rust"):
        adapter_tasks = [task for task in tasks if task.adapter == adapter]
        if not adapter_tasks:
            continue
        roots = sorted({str(Path(path).parent) or "." for path in evidence_by_adapter.get(adapter, [])})
        if not roots:
            roots = ["."]
        tasks = [task for task in tasks if task.adapter != adapter]
        for index, workspace in enumerate(roots):
            suffix = "" if index == 0 else "-" + re.sub(r"[^a-zA-Z0-9]+", "-", workspace).strip("-").lower()
            id_map = {task.task_id: f"{task.task_id}{suffix}" for task in adapter_tasks}
            for task in adapter_tasks:
                clone = task.model_copy(deep=True)
                clone.task_id = id_map[task.task_id]
                clone.target = workspace
                clone.depends_on = [id_map.get(dependency, dependency) for dependency in task.depends_on]
                expanded.append(clone)
    tasks.extend(expanded)
    mode_stages = {
        "QUICK": QUICK_SCAN_STAGES,
        "STANDARD": STANDARD_SCAN_STAGES,
        "FULL": tuple(stage for stage, _ in FULL_AUDIT_STAGES),
    }[mode]
    represented = {STAGE_ALIASES.get(task.stage, task.stage) for task in tasks}
    for index, stage in enumerate(mode_stages, start=1):
        if stage not in represented:
            tasks.append(ScanTask(
                task_id=f"stage-{index:02d}-{stage.lower().replace('_', '-')}",
                stage=stage, adapter="core", tool="qsscope", target=".",
                status="NOT_APPLICABLE",
            ))
    order = {stage: index for index, stage in enumerate(mode_stages)}
    tasks.sort(key=lambda task: (order.get(STAGE_ALIASES.get(task.stage, task.stage), 999), task.task_id))
    return tools, tasks
