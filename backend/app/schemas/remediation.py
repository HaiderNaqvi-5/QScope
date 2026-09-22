"""Strict structured contracts for the v1.3 remediation pipeline."""
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator


Risk = Literal["SAFE", "MODERATE", "HIGH_RISK", "AMBIGUOUS"]
Mode = Literal["SUGGEST_ONLY", "ASSISTED", "AUTONOMOUS"]


class RemediationPlan(BaseModel):
    finding_ids: list[str] = Field(min_length=1)
    root_cause: str = Field(min_length=1, max_length=4000)
    proposed_strategy: str = Field(min_length=1, max_length=4000)
    expected_files: list[str] = Field(min_length=1, max_length=3)
    expected_tests: list[str] = Field(default_factory=list, max_length=50)
    expected_behavior_after_fix: str = Field(min_length=1, max_length=4000)
    risk: Risk
    fix_confidence: float = Field(ge=0, le=1)
    public_api_change: bool = False
    database_change: bool = False
    dependency_change: bool = False

    @model_validator(mode="after")
    def high_risk_flags_are_not_downgraded(self):
        if (self.database_change or self.dependency_change or self.public_api_change) and self.risk in {"SAFE", "MODERATE"}:
            raise ValueError("database, dependency, and public API changes must be HIGH_RISK or AMBIGUOUS")
        return self


class PatchPreflightResult(BaseModel):
    accepted: bool
    outcome: Literal["READY", "PATCH_REJECTED"]
    files: list[str] = Field(default_factory=list)
    changed_lines: int = 0
    reasons: list[str] = Field(default_factory=list)


class RemediationEligibility(BaseModel):
    eligible: bool
    requires_approval: bool
    action: Literal["SUGGEST", "ASSISTED", "AUTO_APPLY", "MANUAL_REVIEW"]
    reasons: list[str] = Field(default_factory=list)


class RemediationPlanRequest(BaseModel):
    mode: Mode = "ASSISTED"
    reproduced: bool = False
    deterministic_static_evidence: bool = False
    impact_radius: dict = Field(default_factory=dict)
    plan: RemediationPlan


class ReproductionRequest(BaseModel):
    """A bounded, non-destructive replay of an API finding before remediation."""
    base_url: str = Field(min_length=1, max_length=2048)
    method: Literal["GET", "HEAD", "OPTIONS"] = "GET"
    endpoint: str = Field(min_length=1, max_length=2048)
    expected_status_codes: list[int] = Field(min_length=1, max_length=20)
    headers: dict[str, str] = Field(default_factory=dict, max_length=30)


class RemediationAttemptResponse(BaseModel):
    model_config = {"from_attributes": True}
    id: str
    project_id: str
    scan_id: str
    finding_id: str
    attempt_number: int
    mode: Mode
    status: str
    risk: Risk
    finding_confidence: float
    fix_confidence: float
    reproduced: bool
    deterministic_static_evidence: bool
    impact_radius: dict
    plan: dict
    eligibility: dict
    patch: str | None
    changed_files: list[str]
    checkpoint: dict
    verification_plan: list[str]
    evidence: dict
    final_outcome: str | None
    created_at: datetime | None
    updated_at: datetime | None


class RemediationPatchRequest(BaseModel):
    patch: str = Field(min_length=1, max_length=100_000)


class RemediationApplyRequest(BaseModel):
    approved: bool = False


class VerificationCheck(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    argv: list[str] = Field(min_length=1, max_length=30)
    working_directory: str = Field(default=".", max_length=2048)
    timeout_seconds: int = Field(default=60, ge=1, le=300)


class RemediationVerifyRequest(BaseModel):
    original: VerificationCheck
    targeted: list[VerificationCheck] = Field(min_length=1, max_length=20)
    regression: list[VerificationCheck] = Field(default_factory=list, max_length=20)


class RemediationQueueItem(BaseModel):
    attempt: RemediationAttemptResponse
    finding_title: str
    severity: str | None
    affected_files: list[str]
    verification_test_count: int
    available_actions: list[Literal["PREVIEW_FIX", "FIX_VERIFY", "SKIP", "MANUAL_REVIEW"]]


class RemediationDispositionRequest(BaseModel):
    disposition: Literal["SKIPPED", "MANUAL_REVIEW_REQUIRED"]
    note: str | None = Field(default=None, max_length=2000)


class SafeFixQueueEntry(BaseModel):
    attempt_id: str
    verification: RemediationVerifyRequest
    approved: bool = False


class SafeFixQueueRequest(BaseModel):
    entries: list[SafeFixQueueEntry] = Field(min_length=1, max_length=50)


class SafeFixQueueResponse(BaseModel):
    project_id: str
    processed: int
    verified: int
    rolled_back: int
    manual_review: int
    attempts: list[RemediationAttemptResponse]


class FixPackCreate(BaseModel):
    root_cause_id: str = Field(min_length=1, max_length=128)
    finding_ids: list[str] = Field(min_length=2, max_length=20)
    correlation_confidence: float = Field(ge=0, le=1)
    proposed_shared_correction: str = Field(min_length=1, max_length=4000)
    risk: Risk
    impact_radius: dict = Field(default_factory=dict)
    verification_scenarios: dict[str, list[VerificationCheck]]


class FixPackResponse(BaseModel):
    model_config = {"from_attributes": True}
    id: str
    project_id: str
    scan_id: str
    root_cause_id: str
    finding_ids: list[str]
    correlation_confidence: float
    proposed_shared_correction: str
    risk: Risk
    impact_radius: dict
    verification_scenarios: dict
    status: str
    created_at: datetime | None
    updated_at: datetime | None
