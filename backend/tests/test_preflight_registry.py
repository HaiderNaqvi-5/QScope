import subprocess

from app.services.preflight import (FULL_AUDIT_STAGES, QUICK_SCAN_STAGES, STANDARD_SCAN_STAGES,
                                    STAGE_ALIASES, build_scan_plan, inspect_tools)
from app.tools.registry import TOOL_REGISTRY


def test_registry_contains_locked_universal_and_ecosystem_tools():
    required = {"semgrep", "gitleaks", "trivy", "osv-scanner", "syft", "jscpd", "lizard",
                "schemathesis", "newman", "playwright", "axe", "lighthouse", "zap", "k6", "jmeter",
                "python", "node", "go", "cargo", "mvn", "php", "dotnet"}
    assert required <= TOOL_REGISTRY.keys()
    assert all(tool.install_guidance for tool in TOOL_REGISTRY.values())
    assert all(tool.categories for tool in TOOL_REGISTRY.values())


def test_missing_required_and_optional_tools_are_distinct(monkeypatch):
    monkeypatch.setattr("app.services.preflight.shutil.which", lambda _name: None)
    statuses = {item.id: item for item in inspect_tools({"languages": [{"value": "Python"}]})}
    assert statuses["python"].status == "MISSING"
    assert statuses["python"].required is True
    assert statuses["semgrep"].status == "OPTIONAL_NOT_INSTALLED"
    assert statuses["semgrep"].guidance


def test_version_timeout_is_visible_as_error(monkeypatch):
    monkeypatch.setattr("app.services.preflight.shutil.which", lambda name: f"/bin/{name}")
    monkeypatch.setattr("app.services.preflight.subprocess.run", lambda *args, **kwargs: (_ for _ in ()).throw(
        subprocess.TimeoutExpired(args[0], 3)))
    status = next(item for item in inspect_tools({"languages": [{"value": "Go"}]}) if item.id == "go")
    assert status.status == "ERROR"
    assert status.available is False


def test_malformed_version_output_is_error(monkeypatch):
    monkeypatch.setattr("app.services.preflight.shutil.which", lambda name: f"/bin/{name}")
    monkeypatch.setattr("app.services.preflight.subprocess.run", lambda *args, **kwargs: subprocess.CompletedProcess(
        args[0], 2, "", "bad version"))
    status = next(item for item in inspect_tools({"languages": [{"value": "Rust"}]}) if item.id == "cargo")
    assert status.status == "ERROR"
    assert status.version == "bad version"


def test_monorepo_tasks_are_expanded_per_manifest_workspace(monkeypatch):
    monkeypatch.setattr("app.services.preflight.inspect_tools", lambda _model: [])
    model = {
        "languages": [{"value": "Python"}],
        "manifest_evidence": {"python": ["apps/api/pyproject.toml", "services/jobs/requirements.txt"]},
        "test_suites": [{"value": "pytest"}],
    }
    _, tasks = build_scan_plan("project", model, "STANDARD")
    python_tests = [task for task in tasks if task.task_id.startswith("python-tests")]
    assert {task.target for task in python_tests} == {"apps/api", "services/jobs"}
    assert all(task.depends_on[0].startswith("python-compile") for task in python_tests)


def test_full_audit_exposes_every_v13_stage_in_locked_order(monkeypatch):
    monkeypatch.setattr("app.services.preflight.inspect_tools", lambda _model: [])
    _, tasks = build_scan_plan("project", {"languages": [], "manifest_evidence": {}}, "FULL")
    expected = [stage for stage, _label in FULL_AUDIT_STAGES]
    represented = []
    for task in tasks:
        stage = STAGE_ALIASES.get(task.stage, task.stage)
        if stage not in represented:
            represented.append(stage)
    assert represented == expected
    assert all(any(STAGE_ALIASES.get(task.stage, task.stage) == stage for task in tasks) for stage in expected)
    assert all(task.status == "NOT_APPLICABLE" for task in tasks if task.task_id.startswith("stage-"))


def test_every_mode_exposes_its_prd_stage_contract(monkeypatch):
    monkeypatch.setattr("app.services.preflight.inspect_tools", lambda _model: [])
    for mode, expected in (("QUICK", QUICK_SCAN_STAGES), ("STANDARD", STANDARD_SCAN_STAGES)):
        _, tasks = build_scan_plan("project", {"languages": [], "manifest_evidence": {}}, mode)
        represented = []
        for task in tasks:
            stage = STAGE_ALIASES.get(task.stage, task.stage)
            if stage not in represented:
                represented.append(stage)
        assert represented == list(expected)


def test_standard_schedules_applicable_api_and_browser_checks(monkeypatch):
    monkeypatch.setattr("app.services.preflight.inspect_tools", lambda _model: [])
    model = {
        "languages": [], "manifest_evidence": {}, "api_specs": {"detected": True},
        "postman_collections": [{"value": "api.postman_collection.json"}],
        "browser_tests": [{"value": "playwright"}], "accessibility_tests": [{"value": "axe"}],
        "performance_tests": [{"value": "lighthouse"}],
        "runtime_targets": [{"base_url": "http://127.0.0.1:3000"}],
    }
    _, tasks = build_scan_plan("project", model, "STANDARD")
    ids = {task.task_id for task in tasks}
    assert {"runtime-api", "runtime-postman", "browser-functional", "browser-accessibility",
            "browser-performance"} <= ids
