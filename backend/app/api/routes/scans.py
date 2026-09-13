"""Scan session endpoints."""
from datetime import datetime
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_session
from app.models import Baseline, Finding, Project, ScanSession
from app.schemas.projects import ProjectModel
from app.schemas.scans import ScanSessionResponse, ScanStartRequest
from app.services.preflight import build_scan_plan
from app.services.runtime import cancel_scan, event_stream, start_scan
from app.services.findings import score_findings
from app.schemas.findings import FindingResponse, ScanReportResponse

router = APIRouter()


def _response(scan: ScanSession) -> ScanSessionResponse:
    approval_required = any(task.get("requires_user_confirmation") for task in (scan.plan or []))
    return ScanSessionResponse(
        id=scan.id, project_id=scan.project_id, mode=scan.mode, status=scan.status or "PENDING",
        approved=scan.approved == "true", approval_required=approval_required,
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
    plan = [task.model_dump() for task in tasks]
    approval_required = any(task.get("requires_user_confirmation") for task in plan)
    session = ScanSession(id=str(uuid4()), project_id=project.id, mode=request.mode,
        status="AWAITING_APPROVAL" if approval_required else "PENDING",
        approved="false", plan=plan, results=[])
    db.add(session)
    await db.commit()
    await db.refresh(session)
    if not approval_required:
        start_scan(session.id, project.root_path, session.plan)
    return _response(session)


@router.post("/scans/{scan_id}/approve", response_model=ScanSessionResponse, status_code=202)
async def approve_scan(scan_id: str, db: AsyncSession = Depends(get_db_session)) -> ScanSessionResponse:
    scan = await db.get(ScanSession, scan_id)
    if not scan:
        raise HTTPException(status_code=404, detail="Scan session not found")
    if scan.status != "AWAITING_APPROVAL":
        raise HTTPException(status_code=409, detail="Scan does not require approval")
    project = await db.get(Project, scan.project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    scan.approved = "true"
    scan.status = "PENDING"
    await db.commit()
    await db.refresh(scan)
    start_scan(scan.id, project.root_path, scan.plan, approved=True)
    return _response(scan)


@router.get("/scans/{scan_id}", response_model=ScanSessionResponse)
async def get_scan(scan_id: str, db: AsyncSession = Depends(get_db_session)) -> ScanSessionResponse:
    scan = await db.get(ScanSession, scan_id)
    if not scan:
        raise HTTPException(status_code=404, detail="Scan session not found")
    return _response(scan)


@router.get("/projects/{project_id}/scans", response_model=list[ScanSessionResponse])
async def list_project_scans(project_id: str, db: AsyncSession = Depends(get_db_session)) -> list[ScanSessionResponse]:
    if not await db.get(Project, project_id):
        raise HTTPException(status_code=404, detail="Project not found")
    scans = (await db.execute(
        select(ScanSession).where(ScanSession.project_id == project_id).order_by(ScanSession.created_at.desc())
    )).scalars().all()
    return [_response(scan) for scan in scans]


@router.post("/scans/{scan_id}/cancel", response_model=ScanSessionResponse)
async def stop_scan(scan_id: str, db: AsyncSession = Depends(get_db_session)) -> ScanSessionResponse:
    scan = await db.get(ScanSession, scan_id)
    if not scan:
        raise HTTPException(status_code=404, detail="Scan session not found")
    if scan.status in {"COMPLETED", "FAILED", "CANCELLED", "ERROR"}:
        return _response(scan)
    if scan.status == "AWAITING_APPROVAL":
        scan.status = "CANCELLED"
        await db.commit()
        await db.refresh(scan)
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


@router.get("/scans/{scan_id}/report", response_model=ScanReportResponse)
async def scan_report(scan_id: str, db: AsyncSession = Depends(get_db_session)) -> ScanReportResponse:
    scan = await db.get(ScanSession, scan_id)
    if not scan:
        raise HTTPException(status_code=404, detail="Scan session not found")
    findings = (await db.execute(select(Finding).where(Finding.scan_id == scan_id))).scalars().all()
    project_id = scan.project_id
    project = await db.get(Project, project_id)
    dependency_count = len((project.project_model or {}).get("dependencies", [])) if project else 0
    api_spec_count = len((project.project_model or {}).get("api_specs", [])) if project else 0
    api_testing_status = "READY" if api_spec_count and any(
        task.get("task_id") == "runtime-api" for task in (scan.plan or [])
    ) else ("SPEC_FOUND_TOOL_MISSING" if api_spec_count else "NOT_CONFIGURED")
    baseline = (await db.execute(
        select(Baseline).where(Baseline.project_id == project_id).order_by(Baseline.created_at.desc())
    )).scalars().first()
    baseline_fingerprints = set(baseline.fingerprints or []) if baseline else set()
    response_findings = []
    for finding in findings:
        response = FindingResponse.model_validate(finding, from_attributes=True)
        response.status = "EXISTING" if finding.fingerprint in baseline_fingerprints else "NEW"
        response_findings.append(response)
    return ScanReportResponse(
        scan_id=scan_id, status=scan.status or "PENDING",
        approved=scan.approved == "true",
        approval_required=any(task.get("requires_user_confirmation") for task in (scan.plan or [])),
        score=score_findings([finding.model_dump() for finding in response_findings]),
        findings=response_findings,
        task_count=len(scan.results or []),
        failed_tasks=sum(1 for result in (scan.results or []) if result.get("status") in {"FAILED", "TIMED_OUT", "TOOL_MISSING"}),
        new_findings=sum(1 for finding in response_findings if finding.status == "NEW"),
        existing_findings=sum(1 for finding in response_findings if finding.status == "EXISTING"),
        dependency_count=dependency_count,
        api_spec_count=api_spec_count,
        api_testing_status=api_testing_status,
    )


@router.get("/scans/{scan_id}/report/export")
async def export_scan_report(
    scan_id: str,
    format: str = Query("json", pattern="^(json|markdown)$"),
    db: AsyncSession = Depends(get_db_session),
) -> Response:
    report = await scan_report(scan_id, db)
    if format == "json":
        import json
        body = json.dumps(report.model_dump(), indent=2, default=str)
        return Response(body, media_type="application/json", headers={
            "Content-Disposition": f'attachment; filename="qsscope-{scan_id}.json"',
        })
    lines = [
        "# QSScope Scan Report", "",
        f"- Scan: `{report.scan_id}`",
        f"- Status: **{report.status}**",
        f"- Score: **{report.score}/100**",
        f"- New findings: **{report.new_findings}**",
        f"- Existing findings: **{report.existing_findings}**", "",
        f"- Dependencies inventoried: **{report.dependency_count}**", "",
        f"- API specs: **{report.api_spec_count}**",
        f"- API testing readiness: **{report.api_testing_status}**", "",
        "## Findings",
    ]
    if report.findings:
        lines.extend(
            f"- **{finding.severity} / {finding.status}** {finding.title}"
            f" — {(finding.file_path + ':' + (finding.line or '')) if finding.file_path else 'project'}"
            f" — {finding.message}"
            for finding in report.findings
        )
    else:
        lines.append("- No normalized findings.")
    return Response("\n".join(lines) + "\n", media_type="text/markdown", headers={
        "Content-Disposition": f'attachment; filename="qsscope-{scan_id}.md"',
    })


@router.post("/scans/{scan_id}/baseline", response_model=ScanReportResponse)
async def create_baseline(scan_id: str, db: AsyncSession = Depends(get_db_session)) -> ScanReportResponse:
    scan = await db.get(ScanSession, scan_id)
    if not scan:
        raise HTTPException(status_code=404, detail="Scan session not found")
    findings = (await db.execute(select(Finding).where(Finding.scan_id == scan_id))).scalars().all()
    db.add(Baseline(id=str(uuid4()), project_id=scan.project_id, fingerprints=[finding.fingerprint for finding in findings]))
    await db.commit()
    return await scan_report(scan_id, db)
