"""Deterministic local project discovery."""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

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
        "backend_targets": [], "api_specs": [], "runtime_targets": [], "database_indicators": [],
        "test_suites": [], "build_commands": [], "run_commands": [],
        "docker": {}, "git": {}, "confidence": {}, "files_scanned": 0,
    }
    detected: dict[str, list[str]] = {}
    manifests: set[str] = set()
    source_files: list[Path] = []

    for current, dirs, files in os.walk(root):
        dirs[:] = sorted(d for d in dirs if d not in IGNORED_DIRS)
        relative = Path(current).relative_to(root)
        for filename in sorted(files):
            path = Path(current) / filename
            rel = str(path.relative_to(root))
            model["files_scanned"] += 1
            if path.suffix in EXTENSIONS:
                source_files.append(path)
                detected.setdefault(EXTENSIONS[path.suffix], []).append(rel)
            if filename in {
                "package.json", "requirements.txt", "pyproject.toml", "poetry.lock",
                "Pipfile", "pom.xml", "build.gradle", "build.gradle.kts",
                "composer.json", "go.mod", "Cargo.toml", "Dockerfile",
                "docker-compose.yml", "docker-compose.yaml", "openapi.yaml",
                "openapi.yml", "openapi.json", "swagger.yaml", "swagger.json",
            }:
                manifests.add(rel)
            if "test" in filename.lower() or "spec" in filename.lower():
                model["test_suites"].append(_evidence("detected-test-files", [rel], "medium"))

    model["languages"] = [
        _evidence(language, files, "high" if len(files) >= 2 else "medium")
        for language, files in sorted(detected.items())
    ]

    def has(name: str) -> list[str]:
        return sorted(path for path in manifests if Path(path).name == name)

    package_json = root / "package.json"
    if package_json.exists():
        model["languages"].append(_evidence("JavaScript", ["package.json"], "high"))
        model["package_managers"].append(_evidence("npm", ["package.json"]))
        try:
            package = json.loads(package_json.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            package = {}
        deps = {**package.get("dependencies", {}), **package.get("devDependencies", {})}
        model["dependencies"].extend(
            {"name": name, "version": str(version), "manifest": "package.json"}
            for name, version in sorted(deps.items())
        )
        if "typescript" in deps:
            model["languages"].append(_evidence("TypeScript", ["package.json"], "high"))
        for dep, framework in {
            "next": "Next.js", "react": "React", "vue": "Vue",
            "express": "Express", "vite": "Vite",
        }.items():
            if dep in deps:
                model["frameworks"].append(_evidence(framework, ["package.json"]))
        scripts = package.get("scripts", {})
        model["build_commands"].extend(
            f"npm run {name}" for name in ("build", "typecheck", "lint") if name in scripts
        )
        if "start" in scripts or "dev" in scripts:
            model["run_commands"].append(f"npm run {'dev' if 'dev' in scripts else 'start'}")

    if "requirements.txt" in {Path(p).name for p in manifests} or "pyproject.toml" in {Path(p).name for p in manifests}:
        model["package_managers"].append(_evidence("pip/pyproject", [p for p in manifests if Path(p).name in {"requirements.txt", "pyproject.toml"}]))
        requirements = root / "requirements.txt"
        if requirements.exists():
            for raw_line in requirements.read_text(errors="ignore").splitlines():
                line = raw_line.strip()
                if line and not line.startswith(("#", "-")):
                    name, _, version = line.partition("==")
                    model["dependencies"].append({"name": name.strip(), "version": version.strip() or "*", "manifest": "requirements.txt"})
        model["frameworks"].extend(
            _evidence(name, files) for name, files in (
                ("FastAPI", ["pyproject.toml"]), ("Django", ["requirements.txt"]),
            ) if any(name.lower() in (root / file).read_text(errors="ignore").lower() for file in files if (root / file).exists())
        )
        if (root / "pyproject.toml").exists() or (root / "setup.cfg").exists():
            model["build_commands"].append("python -m compileall .")
        if any("pytest" in (root / file).read_text(errors="ignore").lower() for file in manifests if (root / file).exists()):
            model["test_suites"].append(_evidence("pytest", ["pyproject.toml"], "high"))

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
        text = (root / "composer.json").read_text(errors="ignore").lower()
        if "laravel/framework" in text:
            model["frameworks"].append(_evidence("Laravel", ["composer.json"]))

    for filename in ("openapi.yaml", "openapi.yml", "openapi.json", "swagger.yaml", "swagger.json"):
        if filename in manifest_names:
            model["api_specs"].append(_evidence("OpenAPI", has(filename)))
    if any(name.startswith("Dockerfile") for name in (Path(p).name for p in manifests)):
        model["docker"] = {"detected": True, "evidence": [p for p in manifests if Path(p).name.startswith("Dockerfile")]}
    for command in model["run_commands"]:
        model["runtime_targets"].append({"command": command, "host": "127.0.0.1", "port": "unconfigured"})
    model["git"] = {"detected": (root / ".git").is_dir()}
    model["confidence"] = {
        "languages": min(1.0, len(model["languages"]) / 3),
        "frameworks": min(1.0, len(model["frameworks"]) / 2),
    }
    return root, model
