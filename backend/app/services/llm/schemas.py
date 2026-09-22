from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class LLMJob(StrEnum):
    EXPLAIN = "EXPLAIN"
    SUGGEST_FIX = "SUGGEST_FIX"
    GENERATE_TEST = "GENERATE_TEST"
    ROOT_CAUSE = "ROOT_CAUSE"


class ContextManifestEntry(BaseModel):
    path: str
    start_line: int
    end_line: int
    sha256: str
    redaction_count: int = 0


class LLMRequest(BaseModel):
    job: LLMJob
    finding: dict[str, Any]
    context: str = Field(default="", max_length=120_000)
    manifest: list[ContextManifestEntry] = Field(default_factory=list, max_length=8)
    model: str
    correlation_id: str


class LLMResult(BaseModel):
    summary: str = Field(min_length=1, max_length=8000)
    root_cause: str | None = Field(default=None, max_length=8000)
    remediation: list[str] = Field(default_factory=list, max_length=20)
    suggested_test: str | None = Field(default=None, max_length=16000)
    unified_diff: str | None = Field(default=None, max_length=50000)
    evidence_level: str = "ADVISORY"


class LLMResponse(BaseModel):
    result: LLMResult
    model: str
    correlation_id: str
    manifest: list[ContextManifestEntry]


class ProviderHealth(BaseModel):
    status: str
    detail: str | None = None


class ModelInfo(BaseModel):
    id: str
