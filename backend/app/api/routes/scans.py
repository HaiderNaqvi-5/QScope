"""Scan session endpoints."""
from datetime import datetime
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_session
from app.models import Project, ScanSession
from app.schemas.projects import ProjectModel
from app.schemas.scans import ScanSessionResponse, ScanStartRequest
from app.services.preflight import build_scan_plan
from app.services.runtime import cancel_scan, event_stream, start_scan

router = APIRouter()


def _response(scan: ScanSession) -> ScanSessionResponse:
    return ScanSessionResponse(
        id=scan.id, project_id=scan.project_id, mode=scan.mode, status=scan.status or "PENDING",
        results=scan.results or [], error=scan.error, created_at=scan.created_at,
        started_at=scan.started_at, completed_at=scan.completed_at,
    )


@router.post("/projects/{project_id}/scans", response_model=ScanSessionResponse, status_code=202)
async def start_project_scan(project_id: str, request: ScanStartRequest, db: AsyncSession = Depends(get_db_session)) -> ScanSessionResponse:
    project = await db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    tools, tasks = build_scan_plan(project.id, ProjectModel.model_validate(project.project_model).model_dump(), request.mode)
    del tools
    session = ScanSession(id=str(uuid4()), project_id=project.id, mode=request.mode, status="PENDING", plan=[task.model_dump() for task in tasks], results=[])
    db.add(session)
    await db.commit()
    await db.refresh(session)
    start_scan(session.id, project.root_path, session.plan)
    return _response(session)


@router.get("/scans/{scan_id}", response_model=ScanSessionResponse)
async def get_scan(scan_id: str, db: AsyncSession = Depends(get_db_session)) -> ScanSessionResponse:
    scan = await db.get(ScanSession, scan_id)
    if not scan:
        raise HTTPException(status_code=404, detail="Scan session not found")
    return _response(scan)


@router.post("/scans/{scan_id}/cancel", response_model=ScanSessionResponse)
async def stop_scan(scan_id: str, db: AsyncSession = Depends(get_db_session)) -> ScanSessionResponse:
    scan = await db.get(ScanSession, scan_id)
    if not scan:
        raise HTTPException(status_code=404, detail="Scan session not found")
    if scan.status in {"COMPLETED", "FAILED", "CANCELLED", "ERROR"}:
        return _response(scan)
    if not cancel_scan(scan_id):
        raise HTTPException(status_code=409, detail="Scan is not currently running")
    scan.status = "CANCELLING"
    await db.commit()
    await db.refresh(scan)
    return _response(scan)


@router.get("/scans/{scan_id}/events")
async def scan_events(scan_id: str, db: AsyncSession = Depends(get_db_session)) -> StreamingResponse:
    if not await db.get(ScanSession, scan_id):
        raise HTTPException(status_code=404, detail="Scan session not found")
    return StreamingResponse(event_stream(scan_id), media_type="text/event-stream")
