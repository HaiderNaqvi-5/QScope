"""Project discovery and scan-plan API schemas."""
from typing import Any, Literal

from pydantic import BaseModel, Field


class ProjectDiscoverRequest(BaseModel):
    root_path: str = Field(..., min_length=1, description="Local project directory")


class RuntimeTarget(BaseModel):
    host: Literal["127.0.0.1", "localhost", "::1"] = "127.0.0.1"
    port: int = Field(..., ge=1, le=65535)
    scheme: Literal["http", "https"] = "http"

    @property
    def base_url(self) -> str:
        host = f"[{self.host}]" if self.host == "::1" else self.host
        return f"{self.scheme}://{host}:{self.port}"


class RuntimeHealthResponse(BaseModel):
    status: Literal["HEALTHY", "UNHEALTHY", "UNREACHABLE", "NOT_CONFIGURED"]
    target: str | None = None
    status_code: int | None = None
    latency_ms: int | None = None
    error: str | None = None


class Evidence(BaseModel):
    value: str
    evidence: list[str] = Field(default_factory=list)
    confidence: Literal["high", "medium", "low"] = "medium"


class ProjectModel(BaseModel):
    languages: list[Evidence] = Field(default_factory=list)
    frameworks: list[Evidence] = Field(default_factory=list)
    package_managers: list[Evidence] = Field(default_factory=list)
    dependencies: list[dict[str, str]] = Field(default_factory=list)
    workspace_roots: list[str] = Field(default_factory=list)
    services: list[Evidence] = Field(default_factory=list)
    frontend_targets: list[Evidence] = Field(default_factory=list)
    backend_targets: list[Evidence] = Field(default_factory=list)
    api_specs: list[Evidence] = Field(default_factory=list)
    graphql_specs: list[Evidence] = Field(default_factory=list)
    postman_collections: list[Evidence] = Field(default_factory=list)
    postman_environments: list[Evidence] = Field(default_factory=list)
    browser_tests: list[Evidence] = Field(default_factory=list)
    accessibility_tests: list[Evidence] = Field(default_factory=list)
    performance_tests: list[Evidence] = Field(default_factory=list)
    security_tests: list[Evidence] = Field(default_factory=list)
    load_tests: list[Evidence] = Field(default_factory=list)
    runtime_targets: list[dict[str, Any]] = Field(default_factory=list)
    database_indicators: list[Evidence] = Field(default_factory=list)
    test_suites: list[Evidence] = Field(default_factory=list)
    build_commands: list[str] = Field(default_factory=list)
    run_commands: list[str] = Field(default_factory=list)
    docker: dict[str, Any] = Field(default_factory=dict)
    git: dict[str, Any] = Field(default_factory=dict)
    confidence: dict[str, float] = Field(default_factory=dict)
    manifest_evidence: dict[str, list[str]] = Field(default_factory=dict)
    unsupported_languages: list[Evidence] = Field(default_factory=list)
    files_scanned: int = 0


class ProjectResponse(BaseModel):
    id: str
    name: str
    root_path: str
    model: ProjectModel


class ToolStatus(BaseModel):
    id: str
    display_name: str
    executable: str
    available: bool
    status: Literal["READY", "MISSING", "INCOMPATIBLE_VERSION", "ERROR", "OPTIONAL_NOT_INSTALLED", "NOT_APPLICABLE"] = "MISSING"
    version: str | None = None
    required: bool = False
    guidance: str | None = None
    reason: str | None = None
    categories: list[str] = Field(default_factory=list)
    adapter: str = "universal"
    license: str | None = None
    output_formats: list[str] = Field(default_factory=list)


class ScanTask(BaseModel):
    task_id: str
    stage: str
    adapter: str
    tool: str
    target: str
    depends_on: list[str] = Field(default_factory=list)
    estimated_cost: Literal["LOW", "MEDIUM", "HIGH"] = "LOW"
    requires_runtime: bool = False
    requires_user_confirmation: bool = False
    status: str = "PENDING"


class ScanPlanResponse(BaseModel):
    project_id: str
    mode: Literal["QUICK", "STANDARD", "FULL"]
    tools: list[ToolStatus]
    tasks: list[ScanTask]
