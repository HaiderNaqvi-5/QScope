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
    score: int
    findings: list[FindingResponse]
    task_count: int
    failed_tasks: int
    new_findings: int = 0
    existing_findings: int = 0
