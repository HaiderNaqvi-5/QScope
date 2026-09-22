"""Manual QA test-case contracts."""
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator

ManualStatus = Literal["NOT_RUN", "PASS", "FAIL", "BLOCKED", "NOT_APPLICABLE"]
Severity = Literal["CRITICAL", "HIGH", "MEDIUM", "LOW", "INFO"]


class ManualTestCreate(BaseModel):
    project_id: str
    module: str = Field(min_length=1, max_length=255)
    feature: str | None = Field(default=None, max_length=255)
    preconditions: list[str] = Field(default_factory=list, max_length=50)
    steps: list[str] = Field(min_length=1, max_length=100)
    expected_result: str = Field(min_length=1, max_length=10_000)
    actual_result: str | None = Field(default=None, max_length=10_000)
    status: ManualStatus = "NOT_RUN"
    severity: Severity | None = None
    notes: str | None = Field(default=None, max_length=10_000)

    @model_validator(mode="after")
    def failed_case_has_severity(self):
        if self.status == "FAIL" and self.severity is None:
            raise ValueError("failed manual tests require severity")
        return self


class ManualTestUpdate(BaseModel):
    module: str | None = Field(default=None, min_length=1, max_length=255)
    feature: str | None = Field(default=None, max_length=255)
    preconditions: list[str] | None = Field(default=None, max_length=50)
    steps: list[str] | None = Field(default=None, min_length=1, max_length=100)
    expected_result: str | None = Field(default=None, min_length=1, max_length=10_000)
    actual_result: str | None = Field(default=None, max_length=10_000)
    status: ManualStatus | None = None
    severity: Severity | None = None
    notes: str | None = Field(default=None, max_length=10_000)
    accepted: bool | None = None


class ManualEvidenceResponse(BaseModel):
    id: str
    original_name: str
    mime_type: str
    sha256: str
    created_at: datetime | None
    model_config = {"from_attributes": True}


class ManualTestResponse(BaseModel):
    id: str
    project_id: str
    module: str
    feature: str | None
    preconditions: list[str]
    steps: list[str]
    expected_result: str
    actual_result: str | None
    status: ManualStatus
    severity: Severity | None
    notes: str | None
    source: str
    accepted: bool
    evidence: list[ManualEvidenceResponse] = Field(default_factory=list)
    created_at: datetime | None
    updated_at: datetime | None
    model_config = {"from_attributes": True}
