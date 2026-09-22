import pytest

from app.adapters.registry import adapter_registry
from app.services.discovery import discover_project
from app.services.preflight import build_scan_plan


@pytest.mark.parametrize(("filename", "content", "language", "adapter"), [
    ("pom.xml", "<project />", "Java", "java"),
    ("composer.json", '{"require":{"laravel/framework":"^11"}}', "PHP", "php"),
    ("go.mod", "module example.test/demo\n", "Go", "go"),
    ("demo.csproj", '<Project Sdk="Microsoft.NET.Sdk" />', "C#", "dotnet"),
    ("Cargo.toml", '[package]\nname="demo"\nversion="0.1.0"', "Rust", "rust"),
])
def test_required_ecosystems_have_evidenced_detection(tmp_path, filename, content, language, adapter):
    workspace = tmp_path / "service"
    workspace.mkdir()
    (workspace / filename).write_text(content)
    _, model = discover_project(str(tmp_path))
    detected = {item["value"] for item in model["languages"]}
    assert language in detected
    assert model["manifest_evidence"][adapter] == [f"service/{filename}"]
    assert "service" in model["workspace_roots"]
    assert adapter_registry()[adapter].detect(model).applicable


def test_gitignore_and_ignore_files_are_respected(tmp_path):
    (tmp_path / ".gitignore").write_text("ignored/\n*.generated.py\n")
    (tmp_path / ".ignore").write_text("private/\n")
    for directory in ("ignored", "private"):
        (tmp_path / directory).mkdir()
        (tmp_path / directory / "secret.py").write_text("print('should not scan')")
    (tmp_path / "visible.py").write_text("print('scan')")
    (tmp_path / "skip.generated.py").write_text("print('skip')")
    _, model = discover_project(str(tmp_path))
    python = next(item for item in model["languages"] if item["value"] == "Python")
    assert python["evidence"] == ["visible.py"]


def test_database_indicator_and_git_metadata(tmp_path):
    (tmp_path / "app.py").write_text("DATABASE_URL = 'sqlite:///local.db'")
    _, model = discover_project(str(tmp_path))
    assert model["database_indicators"][0]["value"] == "SQLite"
    assert model["git"]["detected"] is False


@pytest.mark.parametrize(("filename", "content", "expected_tasks"), [
    ("pom.xml", "<project />", {"java-build", "java-tests"}),
    ("build.gradle", "plugins { id 'java' }", {"java-build", "java-tests"}),
    ("composer.json", "{}", {"php-build", "php-tests"}),
    ("go.mod", "module demo", {"go-vet", "go-tests", "go-staticcheck", "go-vuln"}),
    ("demo.csproj", "<Project />", {"dotnet-build", "dotnet-tests"}),
    ("Cargo.toml", "[package]\nname='demo'", {"rust-check", "rust-clippy", "rust-tests", "rust-audit"}),
])
def test_full_plan_contains_required_native_tasks(tmp_path, filename, content, expected_tasks):
    (tmp_path / filename).write_text(content)
    _, model = discover_project(str(tmp_path))
    _, tasks = build_scan_plan("project", model, "FULL")
    task_ids = {task.task_id for task in tasks}
    assert expected_tasks <= task_ids
    if filename == "build.gradle":
        assert next(task for task in tasks if task.task_id == "java-build").tool == "gradle"


def test_standard_plan_includes_static_quality_engines(tmp_path):
    (tmp_path / "app.py").write_text("value = 1")
    _, model = discover_project(str(tmp_path))
    _, tasks = build_scan_plan("project", model, "STANDARD")
    ids = {task.task_id for task in tasks}
    assert {"python-ruff", "python-mypy", "complexity", "duplication"} <= ids


def test_nested_node_workspaces_contribute_frameworks_commands_and_evidence(tmp_path):
    web = tmp_path / "apps" / "web"
    api = tmp_path / "services" / "api"
    web.mkdir(parents=True)
    api.mkdir(parents=True)
    (tmp_path / "package.json").write_text('{"private": true, "workspaces": ["apps/*", "services/*"]}')
    (web / "package.json").write_text(
        '{"dependencies":{"next":"14","react":"18","typescript":"5"},'
        '"scripts":{"dev":"next dev","build":"next build","test":"jest"}}'
    )
    (api / "package.json").write_text(
        '{"dependencies":{"express":"4"},"scripts":{"start":"node server.js"}}'
    )

    _, model = discover_project(str(tmp_path))

    assert {"Next.js", "React", "Express"} <= {item["value"] for item in model["frameworks"]}
    assert "apps/web/package.json" in next(item for item in model["frameworks"] if item["value"] == "Next.js")["evidence"]
    assert "npm --prefix apps/web run build" in model["build_commands"]
    assert "npm --prefix apps/web run dev" in model["run_commands"]
    assert "npm --prefix services/api run start" in model["run_commands"]
    assert {"Next.js", "React"} <= {item["value"] for item in model["frontend_targets"]}
    assert "Express" in {item["value"] for item in model["backend_targets"]}


def test_nested_python_workspace_contributes_dependencies_and_framework_evidence(tmp_path):
    service = tmp_path / "services" / "catalog"
    service.mkdir(parents=True)
    (service / "pyproject.toml").write_text(
        "[project]\nname='catalog'\ndependencies=['fastapi>=0.110', 'pytest>=8']\n"
    )

    _, model = discover_project(str(tmp_path))

    assert "FastAPI" in {item["value"] for item in model["frameworks"]}
    assert "services/catalog/pyproject.toml" in next(
        item for item in model["frameworks"] if item["value"] == "FastAPI"
    )["evidence"]
    assert {"fastapi", "pytest"} <= {
        item["name"] for item in model["dependencies"] if item["manifest"] == "services/catalog/pyproject.toml"
    }
    assert "services/catalog/pyproject.toml" in next(
        item for item in model["test_suites"] if item["value"] == "pytest"
    )["evidence"]
