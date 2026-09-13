"""Project discovery and scan-plan API schemas."""
from typing import Any, Literal

from pydantic import BaseModel, Field


class ProjectDiscoverRequest(BaseModel):
    root_path: str = Field(..., min_length=1, description="Local project directory")


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
    runtime_targets: list[dict[str, str]] = Field(default_factory=list)
    database_indicators: list[Evidence] = Field(default_factory=list)
    test_suites: list[Evidence] = Field(default_factory=list)
    build_commands: list[str] = Field(default_factory=list)
    run_commands: list[str] = Field(default_factory=list)
    docker: dict[str, Any] = Field(default_factory=dict)
    git: dict[str, Any] = Field(default_factory=dict)
    confidence: dict[str, float] = Field(default_factory=dict)
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
    version: str | None = None
    required: bool = False
    guidance: str | None = None


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
