"""Deterministic local project discovery."""
from __future__ import annotations

import json
import os
import subprocess
import tomllib
from pathlib import Path
from typing import Any

from app.adapters.registry import BUILTIN_ADAPTERS

IGNORED_DIRS = {
    ".git", "node_modules", ".next", "dist", "build", "coverage", ".venv",
    "venv", "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache",
    "vendor", "target", "bin", "obj", ".idea", ".vscode", ".qsscope",
}

EXTENSIONS = {
    ".py": "Python", ".js": "JavaScript", ".jsx": "JavaScript",
    ".ts": "TypeScript", ".tsx": "TypeScript", ".java": "Java",
    ".php": "PHP", ".go": "Go", ".rs": "Rust", ".cs": "C#",
}


def _evidence(value: str, files: list[str], confidence: str = "high") -> dict[str, Any]:
    return {"value": value, "evidence": sorted(set(files)), "confidence": confidence}


def discover_project(root_path: str) -> tuple[Path, dict[str, Any]]:
    """Inspect manifests and source extensions without executing project code."""
    root = Path(root_path).expanduser().resolve()
    if not root.exists() or not root.is_dir():
        raise ValueError("Project root must be an existing directory")
    if not os.access(root, os.R_OK):
        raise ValueError("Project root is not readable")

    model: dict[str, Any] = {
        "languages": [], "frameworks": [], "package_managers": [],
        "dependencies": [],
        "workspace_roots": [], "services": [], "frontend_targets": [],
        "backend_targets": [], "api_specs": [], "graphql_specs": [], "postman_collections": [],
        "postman_environments": [], "browser_tests": [], "accessibility_tests": [],
        "performance_tests": [], "security_tests": [], "load_tests": [],
        "runtime_targets": [], "database_indicators": [],
        "test_suites": [], "build_commands": [], "run_commands": [],
        "docker": {}, "git": {}, "confidence": {}, "manifest_evidence": {},
        "unsupported_languages": [], "files_scanned": 0,
    }
    detected: dict[str, list[str]] = {}
    manifests: set[str] = set()
    source_files: list[Path] = []

    ignore_patterns: list[str] = []
    for ignore_name in (".gitignore", ".ignore"):
        ignore_file = root / ignore_name
        if ignore_file.is_file():
            ignore_patterns.extend(line.strip().lstrip("/") for line in ignore_file.read_text(errors="ignore").splitlines()
                                   if line.strip() and not line.lstrip().startswith(("#", "!")))

    def ignored(relative: Path) -> bool:
        text = relative.as_posix()
        return any(relative.match(pattern.rstrip("/")) or text.startswith(pattern.rstrip("/") + "/")
                   for pattern in ignore_patterns)

    for current, dirs, files in os.walk(root):
        relative_dir = Path(current).relative_to(root)
        dirs[:] = sorted(d for d in dirs if d not in IGNORED_DIRS and not ignored(relative_dir / d))
        relative = Path(current).relative_to(root)
        for filename in sorted(files):
            path = Path(current) / filename
            relative_path = path.relative_to(root)
            if ignored(relative_path):
                continue
            rel = relative_path.as_posix()
            model["files_scanned"] += 1
            if model["files_scanned"] > 100_000:
                raise ValueError("Project exceeds the 100,000-file discovery safety limit")
            if path.suffix in EXTENSIONS:
                source_files.append(path)
                detected.setdefault(EXTENSIONS[path.suffix], []).append(rel)
            if filename in {
                "package.json", "requirements.txt", "pyproject.toml", "poetry.lock",
                "package-lock.json", "npm-shrinkwrap.json",
                "Pipfile", "pom.xml", "build.gradle", "build.gradle.kts",
                "composer.json", "go.mod", "Cargo.toml", "Dockerfile",
                "docker-compose.yml", "docker-compose.yaml", "openapi.yaml",
                "openapi.yml", "openapi.json", "swagger.yaml", "swagger.json",
            }:
                manifests.add(rel)
            if path.suffix in {".csproj", ".sln"}:
                manifests.add(rel)
            if filename.endswith(".postman_collection.json"):
                model["postman_collections"].append(_evidence("Postman collection", [rel]))
            if filename.endswith(".postman_environment.json"):
                model["postman_environments"].append(_evidence("Postman environment", [rel]))
            if path.suffix in {".graphql", ".gql"}:
                model["graphql_specs"].append(_evidence("GraphQL", [rel]))
            if filename in {"k6.js", "loadtest.js", "load-test.js"} or filename.endswith(".k6.js"):
                model["load_tests"].append(_evidence("k6", [rel]))
            if path.suffix == ".jmx":
                model["load_tests"].append(_evidence("JMeter plan", [rel]))
            if filename.lower() in {"zap.yaml", "zap.yml", "zap.conf"}:
                model["security_tests"].append(_evidence("OWASP ZAP", [rel]))
            if filename in {"playwright.config.ts", "playwright.config.js", "playwright.config.mjs", "playwright.config.cjs"}:
                model["browser_tests"].append(_evidence("Playwright", [rel]))
            if filename.endswith(".spec.ts") and "tests" in rel.lower():
                model["browser_tests"].append(_evidence("Playwright test", [rel], "medium"))
            if "test" in filename.lower() or "spec" in filename.lower():
                model["test_suites"].append(_evidence("detected-test-files", [rel], "medium"))

    model["languages"] = [
        _evidence(language, files, "high" if len(files) >= 2 else "medium")
        for language, files in sorted(detected.items())
    ]
    for adapter in BUILTIN_ADAPTERS:
        evidence = sorted(path for path in manifests if Path(path).name in adapter.manifests or Path(path).suffix in adapter.manifests)
        if evidence:
            model["manifest_evidence"][adapter.id] = evidence
            model["workspace_roots"].extend(sorted({str(Path(path).parent) or "." for path in evidence}))
            if adapter.language not in {item["value"] for item in model["languages"]}:
                model["languages"].append(_evidence(adapter.language, evidence))

    def has(name: str) -> list[str]:
        return sorted(path for path in manifests if Path(path).name == name)

    # Parse every discovered package manifest, not just the repository root. A
    # monorepo commonly keeps its actual frontend and API dependencies beneath
    # a root workspace manifest with only convenience scripts.
    for package_manifest in has("package.json"):
        package_json = root / package_manifest
        workspace = Path(package_manifest).parent
        workspace_text = workspace.as_posix()
        command_prefix = "npm run" if workspace_text == "." else f"npm --prefix {workspace_text} run"
        model["languages"].append(_evidence("JavaScript", [package_manifest], "high"))
        model["package_managers"].append(_evidence("npm", [package_manifest]))
        try:
            package = json.loads(package_json.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            package = {}
        deps = {**package.get("dependencies", {}), **package.get("devDependencies", {})}
        model["dependencies"].extend(
            {"name": name, "version": str(version), "manifest": package_manifest}
            for name, version in sorted(deps.items())
        )
        if any(name in deps for name in ("@axe-core/playwright", "axe-playwright", "jest-axe")):
            model["accessibility_tests"].append(_evidence("axe", [package_manifest]))
            model["browser_tests"].append(_evidence("Playwright", [package_manifest], "medium"))
        if "lighthouse" in deps:
            model["performance_tests"].append(_evidence("Lighthouse", [package_manifest]))
            model["browser_tests"].append(_evidence("Playwright", [package_manifest], "medium"))
        if any(name in deps for name in ("graphql", "graphql-request", "@apollo/client", "apollo-server")):
            model["graphql_specs"].append(_evidence("GraphQL dependency", [package_manifest], "medium"))
        for lock_name in ("package-lock.json", "npm-shrinkwrap.json"):
            lock_path = package_json.parent / lock_name
            if not lock_path.exists():
                continue
            try:
                lock = json.loads(lock_path.read_text(encoding="utf-8"))
            except (OSError, UnicodeDecodeError, json.JSONDecodeError):
                lock = {}
            packages = lock.get("packages", {})
            if isinstance(packages, dict):
                for package_path, package_data in sorted(packages.items()):
                    if not package_path or not isinstance(package_data, dict) or "version" not in package_data:
                        continue
                    name = package_path.removeprefix("node_modules/")
                    if name.startswith("node_modules/"):
                        name = name.rsplit("node_modules/", 1)[-1]
                    model["dependencies"].append({
                        "name": name, "version": str(package_data["version"]),
                        "manifest": lock_path.relative_to(root).as_posix(),
                    })
        if "typescript" in deps:
            model["languages"].append(_evidence("TypeScript", [package_manifest], "high"))
        for dep, framework in {
            "next": "Next.js", "react": "React", "vue": "Vue",
            "express": "Express", "vite": "Vite",
        }.items():
            if dep in deps:
                model["frameworks"].append(_evidence(framework, [package_manifest]))
        scripts = package.get("scripts", {})
        model["build_commands"].extend(
            f"{command_prefix} {name}" for name in ("build", "typecheck", "lint") if name in scripts
        )
        if "start" in scripts or "dev" in scripts:
            model["run_commands"].append(f"{command_prefix} {'dev' if 'dev' in scripts else 'start'}")
        if "test" in scripts:
            model["test_suites"].append(_evidence("JavaScript tests", [f"{package_manifest}#scripts.test"]))

    python_manifests = sorted(p for p in manifests if Path(p).name in {"requirements.txt", "pyproject.toml"})
    if python_manifests:
        model["package_managers"].append(_evidence("pip/pyproject", python_manifests))
        for requirement_manifest in (p for p in python_manifests if Path(p).name == "requirements.txt"):
            requirements = root / requirement_manifest
            for raw_line in requirements.read_text(errors="ignore").splitlines():
                line = raw_line.strip()
                if line and not line.startswith(("#", "-")):
                    name, _, version = line.partition("==")
                    model["dependencies"].append({
                        "name": name.strip(), "version": version.strip() or "*", "manifest": requirement_manifest,
                    })
        for pyproject_manifest in (p for p in python_manifests if Path(p).name == "pyproject.toml"):
            pyproject = root / pyproject_manifest
            try:
                project_data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
            except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError):
                project_data = {}
            pyproject_dependencies = project_data.get("project", {}).get("dependencies", [])
            if isinstance(pyproject_dependencies, list):
                for requirement in pyproject_dependencies:
                    text = str(requirement).strip()
                    if text:
                        name = text.split("[", 1)[0].split(";", 1)[0]
                        for operator in ("==", ">=", "<=", "~=", "!=", ">", "<"):
                            if operator in name:
                                name, version = name.split(operator, 1)
                                model["dependencies"].append({
                                    "name": name.strip(), "version": f"{operator}{version.strip()}",
                                    "manifest": pyproject_manifest,
                                })
                                break
                        else:
                            model["dependencies"].append({
                                "name": name.strip(), "version": "*", "manifest": pyproject_manifest,
                            })
        model["frameworks"].extend(
            _evidence(name, [manifest])
            for name, manifest in (("FastAPI", manifest) for manifest in python_manifests)
            if name.lower() in (root / manifest).read_text(errors="ignore").lower()
        )
        model["frameworks"].extend(
            _evidence("Django", [manifest]) for manifest in python_manifests
            if "django" in (root / manifest).read_text(errors="ignore").lower()
        )
        if any(Path(manifest).name == "pyproject.toml" for manifest in python_manifests) or (root / "setup.cfg").exists():
            model["build_commands"].append("python -m compileall .")
        pytest_evidence = [manifest for manifest in python_manifests
                           if "pytest" in (root / manifest).read_text(errors="ignore").lower()]
        if pytest_evidence:
            model["test_suites"].append(_evidence("pytest", pytest_evidence, "high"))

    manifest_names = {Path(p).name for p in manifests}
    for filename, manager in {
        "pom.xml": "Maven", "build.gradle": "Gradle", "build.gradle.kts": "Gradle",
        "composer.json": "Composer", "go.mod": "Go modules", "Cargo.toml": "Cargo",
    }.items():
        if filename in manifest_names:
            model["package_managers"].append(_evidence(manager, has(filename)))
    if "pom.xml" in manifest_names or "build.gradle" in manifest_names or "build.gradle.kts" in manifest_names:
        model["languages"].append(_evidence("Java", has("pom.xml") + has("build.gradle") + has("build.gradle.kts")))
    if "composer.json" in manifest_names:
        model["languages"].append(_evidence("PHP", has("composer.json")))
        text = "\n".join((root / path).read_text(errors="ignore").lower() for path in has("composer.json"))
        if "laravel/framework" in text:
            model["frameworks"].append(_evidence("Laravel", has("composer.json")))

    command_map = {
        "Java": (["mvn compile"], ["mvn test"]), "PHP": (["composer validate --no-check-publish"], ["vendor/bin/phpunit"]),
        "Go": (["go vet ./..."], ["go test ./..."]), "C#": (["dotnet build --no-restore"], ["dotnet test --no-restore"]),
        "Rust": (["cargo check", "cargo clippy -- -D warnings"], ["cargo test"]),
    }
    language_values = {item["value"] for item in model["languages"]}
    for language, (builds, _tests) in command_map.items():
        if language in language_values:
            model["build_commands"].extend(builds)
            model["test_suites"].append(_evidence(f"{language} native tests", model["manifest_evidence"].get(
                {"Java": "java", "PHP": "php", "Go": "go", "C#": "dotnet", "Rust": "rust"}[language], [])))
    for path in source_files:
        try:
            sample = path.read_text(errors="ignore")[:20_000].lower()
        except OSError:
            continue
        rel = path.relative_to(root).as_posix()
        for marker, database in (("postgres", "PostgreSQL"), ("mysql", "MySQL"), ("sqlite", "SQLite"),
                                 ("mongodb", "MongoDB"), ("redis", "Redis")):
            if marker in sample and database not in {item["value"] for item in model["database_indicators"]}:
                model["database_indicators"].append(_evidence(database, [rel], "medium"))

    for filename in ("openapi.yaml", "openapi.yml", "openapi.json", "swagger.yaml", "swagger.json"):
        if filename in manifest_names:
            model["api_specs"].append(_evidence("OpenAPI", has(filename)))
    if any(name.startswith("Dockerfile") for name in (Path(p).name for p in manifests)):
        model["docker"] = {"detected": True, "evidence": [p for p in manifests if Path(p).name.startswith("Dockerfile")]}
    frontend_frameworks = {"React", "Next.js", "Vue", "Vite", "Angular", "Svelte"}
    backend_frameworks = {"FastAPI", "Django", "Express", "Laravel", "Spring", "ASP.NET"}
    for framework in model["frameworks"]:
        if framework["value"] in frontend_frameworks:
            model["frontend_targets"].append(_evidence(framework["value"], framework["evidence"],
                                                        framework.get("confidence", "medium")))
        if framework["value"] in backend_frameworks:
            model["backend_targets"].append(_evidence(framework["value"], framework["evidence"],
                                                       framework.get("confidence", "medium")))
    for workspace in model["workspace_roots"]:
        if workspace != ".":
            model["services"].append(_evidence(Path(workspace).name or workspace, [workspace], "medium"))
    for command in model["run_commands"]:
        model["runtime_targets"].append({"command": command, "host": "127.0.0.1", "port": "unconfigured"})
    model["workspace_roots"] = sorted(set(model["workspace_roots"]))
    model["languages"] = list({item["value"]: item for item in model["languages"]}.values())
    model["frameworks"] = list({item["value"]: item for item in model["frameworks"]}.values())
    git_dir = (root / ".git").is_dir()
    model["git"] = {"detected": git_dir}
    if git_dir:
        for key, argv in (("branch", ["git", "branch", "--show-current"]), ("commit", ["git", "rev-parse", "HEAD"])):
            try:
                value = subprocess.run(argv, cwd=root, capture_output=True, text=True, timeout=2, check=False).stdout.strip()
            except (OSError, subprocess.TimeoutExpired):
                value = ""
            if value:
                model["git"][key] = value
    model["confidence"] = {
        "languages": min(1.0, len(model["languages"]) / 3),
        "frameworks": min(1.0, len(model["frameworks"]) / 2),
    }
    return root, model
