"""Canonical finding query, detail, and workflow endpoints."""
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_session
from app.models import Finding, FindingHistory
from app.schemas.findings import FindingResponse, FindingStatusUpdate

router = APIRouter()


@router.get("/scans/{scan_id}/findings", response_model=list[FindingResponse])
async def scan_findings(scan_id: str, severity: str | None = None, category: str | None = None,
                        tool: str | None = None, status: str | None = None,
                        query: str | None = None, offset: int = Query(0, ge=0), limit: int = Query(100, ge=1, le=500),
                        db: AsyncSession = Depends(get_db_session)) -> list[FindingResponse]:
    statement = select(Finding).where(Finding.scan_id == scan_id)
    for column, value in ((Finding.severity, severity), (Finding.category, category),
                          (Finding.tool, tool), (Finding.status, status)):
        if value:
            statement = statement.where(column == value)
    if query:
        escaped = query.replace("%", "\\%").replace("_", "\\_")
        statement = statement.where(Finding.title.ilike(f"%{escaped}%", escape="\\"))
    rows = (await db.execute(statement.order_by(Finding.created_at, Finding.id).offset(offset).limit(limit))).scalars().all()
    return [FindingResponse.model_validate(row) for row in rows]


@router.get("/findings/{finding_id}", response_model=FindingResponse)
async def finding_detail(finding_id: str, db: AsyncSession = Depends(get_db_session)) -> FindingResponse:
    finding = await db.get(Finding, finding_id)
    if finding is None:
        raise HTTPException(404, "Finding not found")
    return FindingResponse.model_validate(finding)


@router.patch("/findings/{finding_id}/status", response_model=FindingResponse)
async def update_finding_status(finding_id: str, update: FindingStatusUpdate,
                                db: AsyncSession = Depends(get_db_session)) -> FindingResponse:
    finding = await db.get(Finding, finding_id)
    if finding is None:
        raise HTTPException(404, "Finding not found")
    old_status = finding.status
    finding.status = update.status
    db.add(FindingHistory(id=str(uuid4()), finding_id=finding.id, old_status=old_status,
                          new_status=update.status, note=update.note))
    await db.commit()
    await db.refresh(finding)
    return FindingResponse.model_validate(finding)
