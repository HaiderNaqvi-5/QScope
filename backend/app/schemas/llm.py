from datetime import datetime

from pydantic import BaseModel

from app.services.llm.schemas import ContextManifestEntry, LLMJob, LLMResult, ModelInfo


class DisclosureResponse(BaseModel):
    project_id: str
    acknowledged: bool
    policy_version: str
    acknowledged_at: datetime | None = None
    disclosure: str


class AIActionRequest(BaseModel):
    job: LLMJob


class AIActionResponse(BaseModel):
    status: str
    result: LLMResult | None = None
    model: str | None = None
    correlation_id: str | None = None
    manifest: list[ContextManifestEntry] = []
    reason: str | None = None


class ModelsResponse(BaseModel):
    models: list[ModelInfo]

