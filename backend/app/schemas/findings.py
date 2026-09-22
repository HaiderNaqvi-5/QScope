"""Finding and report response schemas."""
from typing import Literal

from pydantic import BaseModel, Field


class FindingResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: str
    scan_id: str
    title: str
    severity: str | None
    tool: str
    stage: str
    file_path: str | None
    line: str | None
    message: str
    status: str
    baseline_state: Literal["NEW", "EXISTING"] | None = None
    category: str = "CODE_QUALITY"
    subcategory: str | None = None
    description: str = ""
    confidence: float = 0.75
    rule_id: str | None = None
    start_line: int | None = None
    end_line: int | None = None
    endpoint: str | None = None
    evidence: dict = Field(default_factory=dict)
    raw_artifact_id: str | None = None
    why_it_matters: str = ""
    recommendation: str = ""
    suggested_patch: str | None = None
    suggested_test: str | None = None
    sources: list[dict] = Field(default_factory=list)
    correlation_key: str | None = None


class ScanReportResponse(BaseModel):
    scan_id: str
    status: str
    approved: bool = False
    approval_required: bool = False
    score: int
    grade: str
    release_readiness: Literal["RELEASE READY", "READY WITH WARNINGS", "NOT READY", "INCOMPLETE AUDIT"]
    release_blockers: list[str] = Field(default_factory=list)
    is_complete_audit: bool = True
    incomplete_reasons: list[str] = Field(default_factory=list)
    findings: list[FindingResponse]
    task_count: int
    failed_tasks: int
    new_findings: int = 0
    existing_findings: int = 0
    resolved_findings: int = 0
    dependency_count: int = 0
    api_spec_count: int = 0
    api_collection_count: int = 0
    api_testing_status: str = "NOT_CONFIGURED"
    security_testing_status: str = "NOT_CONFIGURED"
    load_testing_status: str = "NOT_CONFIGURED"
    accessibility_status: str = "NOT_CONFIGURED"
    performance_status: str = "NOT_CONFIGURED"
    manual_test_count: int = 0
    manual_test_failures: int = 0
    manual_tests: list[dict] = Field(default_factory=list)
    remediation_count: int = 0
    remediation_verified: int = 0
    remediation_rolled_back: int = 0
    remediation_manual_review: int = 0
    remediations: list[dict] = Field(default_factory=list)
    fix_pack_count: int = 0
    fix_packs: list[dict] = Field(default_factory=list)
    generated_test_count: int = 0
    generated_test_passed: int = 0
    generated_test_failed: int = 0
    generated_test_blocked: int = 0
    generated_tests: list[dict] = Field(default_factory=list)
    behavior_coverage_total: int = 0
    behavior_coverage_covered: int = 0
    behavior_coverage_partial: int = 0
    behavior_coverage_untested: int = 0
    behavior_coverage_unknown: int = 0
    behavior_coverage: list[dict] = Field(default_factory=list)
    project_information: dict = Field(default_factory=dict)
    architecture: dict = Field(default_factory=dict)
    tool_coverage: list[dict] = Field(default_factory=list)
    evidence_timeline: list[dict] = Field(default_factory=list)
    report_sections: list[dict] = Field(default_factory=list)


class FindingStatusUpdate(BaseModel):
    status: Literal["OPEN", "ACKNOWLEDGED", "FIXED_PENDING_VERIFY", "VERIFIED_FIXED", "FALSE_POSITIVE", "ACCEPTED_RISK"]
    note: str | None = Field(default=None, max_length=2000)
