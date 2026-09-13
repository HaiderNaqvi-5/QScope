"""Finding and report response schemas."""
from pydantic import BaseModel


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


class ScanReportResponse(BaseModel):
    scan_id: str
    status: str
    approved: bool = False
    approval_required: bool = False
    score: int
    findings: list[FindingResponse]
    task_count: int
    failed_tasks: int
    new_findings: int = 0
    existing_findings: int = 0
    dependency_count: int = 0
    api_spec_count: int = 0
    api_collection_count: int = 0
    api_testing_status: str = "NOT_CONFIGURED"
