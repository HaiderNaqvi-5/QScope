"""Built-in ecosystem adapter registry and deterministic build/test metadata."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.adapters.base import AdapterTask, DetectionResult, ToolRequirement


@dataclass(frozen=True)
class EcosystemAdapter:
    id: str
    display_name: str
    language: str
    manifests: tuple[str, ...]
    build_commands: tuple[tuple[str, ...], ...]
    test_commands: tuple[tuple[str, ...], ...]
    tools: tuple[str, ...]

    def detect(self, project_model: dict[str, Any]) -> DetectionResult:
        evidence = tuple(project_model.get("manifest_evidence", {}).get(self.id, []))
        return DetectionResult(bool(evidence), evidence, 0.98 if evidence else 0.0)

    def preflight(self, project_model: dict[str, Any]) -> list[ToolRequirement]:
        if not self.detect(project_model).applicable:
            return []
        return [ToolRequirement(tool, tool == self.tools[0], f"{self.display_name} analysis") for tool in self.tools]

    def plan(self, project_model: dict[str, Any], scan_mode: str) -> list[AdapterTask]:
        if not self.detect(project_model).applicable:
            return []
        commands = self.build_commands + self.test_commands
        return [AdapterTask(f"{self.id}-{i}", command[0], command) for i, command in enumerate(commands)]

    def normalize(self, raw_result: dict[str, Any], context: dict[str, Any]) -> list[dict[str, Any]]:
        return list(raw_result.get("findings", []))


BUILTIN_ADAPTERS = (
    EcosystemAdapter("javascript", "JavaScript / TypeScript", "JavaScript", ("package.json",),
                     (("npm", "run", "build"),), (("npm", "test", "--", "--runInBand"),), ("npm", "node", "eslint", "tsc", "knip")),
    EcosystemAdapter("python", "Python", "Python", ("pyproject.toml", "requirements.txt", "Pipfile"),
                     (("python", "-m", "compileall", "."),), (("python", "-m", "pytest"),), ("python", "ruff", "mypy", "pytest")),
    EcosystemAdapter("java", "Java", "Java", ("pom.xml", "build.gradle", "build.gradle.kts"),
                     (("mvn", "compile"),), (("mvn", "test"),), ("mvn", "gradle", "java")),
    EcosystemAdapter("php", "PHP", "PHP", ("composer.json",),
                     (("composer", "validate", "--no-check-publish"),), (("php", "vendor/bin/phpunit"),), ("php", "composer", "phpstan", "psalm")),
    EcosystemAdapter("go", "Go", "Go", ("go.mod",),
                     (("go", "vet", "./..."),), (("go", "test", "./..."),), ("go", "staticcheck", "govulncheck")),
    EcosystemAdapter("dotnet", ".NET", "C#", (".sln", ".csproj"),
                     (("dotnet", "build", "--no-restore"),), (("dotnet", "test", "--no-restore"),), ("dotnet",)),
    EcosystemAdapter("rust", "Rust", "Rust", ("Cargo.toml",),
                     (("cargo", "check"), ("cargo", "clippy", "--", "-D", "warnings")), (("cargo", "test"),), ("cargo",)),
)


def adapter_registry() -> dict[str, EcosystemAdapter]:
    return {adapter.id: adapter for adapter in BUILTIN_ADAPTERS}
