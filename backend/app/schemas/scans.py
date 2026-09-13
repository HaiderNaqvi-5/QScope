"""Scan execution API schemas."""
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class ScanStartRequest(BaseModel):
    mode: Literal["QUICK", "STANDARD", "FULL"] = "STANDARD"


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
    status: str
    results: list[ScanResult] = Field(default_factory=list)
    error: str | None = None
    created_at: datetime | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None


class ScanEvent(BaseModel):
    session_id: str
    status: str
    task_id: str | None = None
    message: str
    result: dict[str, Any] | None = None
