"""Contracts for bounded mutation/test-strength analysis."""
from typing import Literal

from pydantic import BaseModel, Field


class MutationRunRequest(BaseModel):
    scan_id: str | None = None
    engine: Literal["AUTO", "MUTMUT", "STRYKER"] = "AUTO"
    timeout_seconds: int = Field(default=300, ge=10, le=600)


class MutationRunResponse(BaseModel):
    project_id: str
    scan_id: str | None
    engine: str | None
    status: Literal["COMPLETED", "FAILED", "TIMED_OUT", "NOT_APPLICABLE", "TOOL_MISSING"]
    mutation_score: float | None = None
    killed: int = 0
    survived: int = 0
    total: int = 0
    evidence: dict = Field(default_factory=dict)
    message: str
