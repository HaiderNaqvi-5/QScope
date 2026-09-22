from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class BehaviorCoverageResponse(BaseModel):
    model_config = {"from_attributes": True}
    id: str
    project_id: str
    scan_id: str | None
    capability_key: str
    category: str
    title: str
    criticality: Literal["CRITICAL", "HIGH", "NORMAL"]
    coverage_status: Literal["COVERED", "PARTIALLY_COVERED", "UNTESTED", "UNKNOWN"]
    source: str
    evidence: dict
    fingerprint: str
    created_at: datetime | None
    updated_at: datetime | None


class BehaviorCoverageSummary(BaseModel):
    total: int
    covered: int
    partially_covered: int
    untested: int
    unknown: int
    records: list[BehaviorCoverageResponse]
