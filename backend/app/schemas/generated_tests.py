from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class GeneratedTestCaseResponse(BaseModel):
    model_config = {"from_attributes": True}
    id: str
    project_id: str
    scan_id: str | None
    category: Literal["CONTRACT", "LOGICAL", "EDGE", "DATA_INTEGRITY", "CONCURRENCY", "RESILIENCE", "MUTATION"]
    title: str
    method: str
    endpoint: str
    actor: str | None
    input_data: dict
    expected: dict
    status: str
    evidence: dict
    source_path: str
    fingerprint: str
    created_at: datetime | None


class GenerationResponse(BaseModel):
    project_id: str
    generated: int
    total: int
    cases: list[GeneratedTestCaseResponse]


class GeneratedTestRunRequest(BaseModel):
    base_url: str = Field(min_length=1, max_length=2048)
    scan_id: str | None = None
    case_ids: list[str] = Field(default_factory=list, max_length=500)
    actor_headers: dict[str, str] = Field(default_factory=dict)
    actor_profiles: dict[str, dict[str, str]] = Field(default_factory=dict)


class GeneratedTestRunResponse(BaseModel):
    total: int
    passed: int
    failed: int
    blocked: int
    results: list[GeneratedTestCaseResponse]


class DataIntegrityRunRequest(BaseModel):
    database_path: str = Field(min_length=1, max_length=2048)
    scan_id: str | None = None
