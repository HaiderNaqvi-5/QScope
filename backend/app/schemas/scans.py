"""Scan execution API schemas."""
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field
from app.schemas.projects import RuntimeTarget


class ScanStartRequest(BaseModel):
    mode: Literal["QUICK", "STANDARD", "FULL"] = "STANDARD"
    runtime_target: RuntimeTarget | None = None


class ScanResult(BaseModel):
    task_id: str
    status: str
    output: str = ""
    exit_code: int | None = None
    duration_ms: int | None = None


class ScanSessionResponse(BaseModel):
    id: str
    project_id: str
    mode: str
    approved: bool = False
    approval_required: bool = False
    status: str
    results: list[ScanResult] = Field(default_factory=list)
    error: str | None = None
    created_at: datetime | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    git_commit: str | None = None
    git_branch: str | None = None
    project_fingerprint: str | None = None
    overall_score: int | None = None
    is_complete_audit: bool | None = None
    release_readiness: str | None = None
    release_blockers: list[str] = Field(default_factory=list)


class ReportHistoryResponse(BaseModel):
    id: str
    scan_id: str
    format: str
    created_at: datetime | None = None


class ScanEvent(BaseModel):
    session_id: str
    status: str
    task_id: str | None = None
    message: str
    result: dict[str, Any] | None = None


class ScanTaskResponse(BaseModel):
    model_config = {"from_attributes": True}
    id: str
    scan_id: str
    task_key: str
    stage: str
    tool: str
    adapter: str
    target: str
    status: str
    depends_on: list[str]
    requires_confirmation: bool
    started_at: datetime | None
    completed_at: datetime | None
    exit_code: int | None
    duration_ms: int | None
    summary: str | None


class PersistedScanEvent(BaseModel):
    model_config = {"from_attributes": True}
    id: str
    scan_id: str
    event: str
    task_id: str | None
    payload: dict[str, Any]
    created_at: datetime | None
