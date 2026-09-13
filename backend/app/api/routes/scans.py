"""Scan session endpoints."""
from datetime import datetime
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_session
from app.models import Baseline, Finding, Project, Report, ScanSession
from app.schemas.projects import ProjectModel
from app.schemas.scans import ReportHistoryResponse, ScanSessionResponse, ScanStartRequest
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
    model = ProjectModel.model_validate(project.project_model).model_dump()
    if request.runtime_target:
        model["runtime_targets"] = [{
            "host": request.runtime_target.host,
            "port": request.runtime_target.port,
            "scheme": request.runtime_target.scheme,
            "base_url": request.runtime_target.base_url,
        }]
        project.project_model = model
    tools, tasks = build_scan_plan(project.id, model, request.mode)
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
    graphql_spec_count = len((project.project_model or {}).get("graphql_specs", [])) if project else 0
    postman_count = len((project.project_model or {}).get("postman_collections", [])) if project else 0
    runtime_target_configured = any(
        task.get("task_id") in {"runtime-api", "runtime-graphql", "runtime-postman"} and task.get("target") != "unconfigured"
        for task in (scan.plan or [])
    )
    api_task_present = any(task.get("task_id") in {"runtime-api", "runtime-graphql", "runtime-postman"} for task in (scan.plan or []))
    api_source_count = api_spec_count + graphql_spec_count + postman_count
    api_testing_status = "READY" if api_source_count and runtime_target_configured and api_task_present else (
        "API_SOURCE_FOUND_TARGET_REQUIRED" if api_source_count else "NOT_CONFIGURED"
    )
    security_task = next((task for task in (scan.plan or []) if task.get("task_id") == "runtime-zap"), None)
    load_task = next((task for task in (scan.plan or []) if task.get("task_id") in {"runtime-k6", "runtime-jmeter"}), None)
    security_status = "READY" if security_task and security_task.get("target") != "unconfigured" else (
        "TARGET_REQUIRED" if security_task else "NOT_CONFIGURED"
    )
    load_status = "READY" if load_task and load_task.get("target") != "unconfigured" else (
        "TARGET_REQUIRED" if load_task else "NOT_CONFIGURED"
    )
    accessibility_task = next((task for task in (scan.plan or []) if task.get("task_id") == "browser-accessibility"), None)
    performance_task = next((task for task in (scan.plan or []) if task.get("task_id") == "browser-performance"), None)
    accessibility_status = "READY" if accessibility_task and accessibility_task.get("target") != "unconfigured" else (
        "TARGET_REQUIRED" if accessibility_task else "NOT_CONFIGURED"
    )
    performance_status = "READY" if performance_task and performance_task.get("target") != "unconfigured" else (
        "TARGET_REQUIRED" if performance_task else "NOT_CONFIGURED"
    )
    baseline = (await db.execute(
        select(Baseline).where(Baseline.project_id == project_id).order_by(Baseline.created_at.desc())
    )).scalars().first()
    baseline_fingerprints = set(baseline.fingerprints or []) if baseline else set()
    current_fingerprints = {finding.fingerprint for finding in findings}
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
        resolved_findings=len(baseline_fingerprints - current_fingerprints),
        dependency_count=dependency_count,
        api_spec_count=api_spec_count,
        api_collection_count=postman_count,
        api_testing_status=api_testing_status,
        security_testing_status=security_status,
        load_testing_status=load_status,
        accessibility_status=accessibility_status,
        performance_status=performance_status,
    )


@router.get("/scans/{scan_id}/report/export")
async def export_scan_report(
    scan_id: str,
    format: str = Query("json", pattern="^(json|markdown|html|docx|pdf)$"),
    db: AsyncSession = Depends(get_db_session),
) -> Response:
    scan = await db.get(ScanSession, scan_id)
    if not scan:
        raise HTTPException(status_code=404, detail="Scan session not found")
    report = await scan_report(scan_id, db)
    db.add(Report(id=str(uuid4()), scan_id=scan_id, format=format))
    await db.commit()
    if format == "json":
        import json
        body = json.dumps(report.model_dump(), indent=2, default=str)
        return Response(body, media_type="application/json", headers={
            "Content-Disposition": f'attachment; filename="qsscope-{scan_id}.json"',
        })
    if format == "html":
        from html import escape
        finding_rows = "".join(
            f"<tr><td>{escape(finding.severity or '')}</td>"
            f"<td>{escape(finding.status)}</td><td>{escape(finding.title)}</td>"
            f"<td>{escape(finding.message)}</td></tr>"
            for finding in report.findings
        ) or '<tr><td colspan="4">No normalized findings.</td></tr>'
        body = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>QSScope Scan Report</title>
<style>body{{font:16px system-ui,sans-serif;max-width:1100px;margin:2rem auto;padding:0 1rem;color:#172033}}
table{{border-collapse:collapse;width:100%}}th,td{{border:1px solid #d5dbe5;padding:.6rem;text-align:left}}
th{{background:#eef2f7}}</style></head><body>
<h1>QSScope Scan Report</h1><p>Scan: <code>{escape(report.scan_id)}</code></p>
<p>Status: <strong>{escape(report.status)}</strong> · Score: <strong>{report.score}/100</strong></p>
<p>New: {report.new_findings} · Existing: {report.existing_findings} · Resolved: {report.resolved_findings}</p>
<h2>Findings</h2><table><thead><tr><th>Severity</th><th>Status</th><th>Title</th><th>Message</th></tr></thead>
<tbody>{finding_rows}</tbody></table></body></html>"""
        return Response(body, media_type="text/html", headers={
            "Content-Disposition": f'attachment; filename="qsscope-{scan_id}.html"',
        })
    if format == "docx":
        from io import BytesIO
        from docx import Document

        document = Document()
        document.add_heading("QSScope Scan Report", level=1)
        document.add_paragraph(f"Scan: {report.scan_id}")
        document.add_paragraph(f"Status: {report.status} | Score: {report.score}/100")
        document.add_paragraph(
            f"New: {report.new_findings} | Existing: {report.existing_findings} | "
            f"Resolved: {report.resolved_findings}"
        )
        document.add_heading("Findings", level=2)
        if report.findings:
            table = document.add_table(rows=1, cols=4)
            table.style = "Table Grid"
            for cell, heading in zip(table.rows[0].cells, ("Severity", "Status", "Title", "Message")):
                cell.text = heading
            for finding in report.findings:
                cells = table.add_row().cells
                cells[0].text = finding.severity or ""
                cells[1].text = finding.status
                cells[2].text = finding.title
                cells[3].text = finding.message
        else:
            document.add_paragraph("No normalized findings.")
        buffer = BytesIO()
        document.save(buffer)
        return Response(buffer.getvalue(), media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document", headers={
            "Content-Disposition": f'attachment; filename="qsscope-{scan_id}.docx"',
        })
    if format == "pdf":
        from html import escape

        finding_rows = "".join(
            f"<tr><td>{escape(finding.severity or '')}</td>"
            f"<td>{escape(finding.status)}</td><td>{escape(finding.title)}</td>"
            f"<td>{escape(finding.message)}</td></tr>"
            for finding in report.findings
        ) or "<tr><td colspan='4'>No normalized findings.</td></tr>"
        html_body = f"""<!doctype html><html><head><meta charset="utf-8">
<style>body{{font:12px Arial,sans-serif;margin:32px;color:#172033}}
h1{{font-size:24px}}table{{border-collapse:collapse;width:100%}}
th,td{{border:1px solid #ccd3df;padding:6px;text-align:left;vertical-align:top}}
th{{background:#eef2f7}}</style></head><body>
<h1>QSScope Scan Report</h1><p>Scan: <code>{escape(report.scan_id)}</code></p>
<p>Status: <strong>{escape(report.status)}</strong> · Score: <strong>{report.score}/100</strong></p>
<p>New: {report.new_findings} · Existing: {report.existing_findings} · Resolved: {report.resolved_findings}</p>
<h2>Findings</h2><table><thead><tr><th>Severity</th><th>Status</th><th>Title</th><th>Message</th></tr></thead>
<tbody>{finding_rows}</tbody></table></body></html>"""
        try:
            from playwright.async_api import Error as PlaywrightError
            from playwright.async_api import async_playwright
        except ImportError as exc:
            raise HTTPException(
                status_code=503,
                detail=f"PDF renderer unavailable; install Playwright Chromium browsers: {exc.__class__.__name__}",
            ) from exc
        try:
            async with async_playwright() as playwright:
                browser = await playwright.chromium.launch()
                try:
                    page = await browser.new_page()
                    await page.set_content(html_body, wait_until="load")
                    pdf = await page.pdf(format="A4", print_background=True)
                finally:
                    await browser.close()
        except (OSError, RuntimeError, PlaywrightError) as exc:
            raise HTTPException(
                status_code=503,
                detail=f"PDF renderer unavailable; install Playwright Chromium browsers: {exc.__class__.__name__}",
            ) from exc
        return Response(pdf, media_type="application/pdf", headers={
            "Content-Disposition": f'attachment; filename="qsscope-{scan_id}.pdf"',
        })
    lines = [
        "# QSScope Scan Report", "",
        f"- Scan: `{report.scan_id}`",
        f"- Status: **{report.status}**",
        f"- Score: **{report.score}/100**",
        f"- New findings: **{report.new_findings}**",
        f"- Existing findings: **{report.existing_findings}**", "",
        f"- Resolved findings since baseline: **{report.resolved_findings}**", "",
        f"- Dependencies inventoried: **{report.dependency_count}**", "",
        f"- API specs: **{report.api_spec_count}**",
        f"- Postman collections: **{report.api_collection_count}**",
        f"- API testing readiness: **{report.api_testing_status}**", "",
        f"- Security testing readiness: **{report.security_testing_status}**",
        f"- Load testing readiness: **{report.load_testing_status}**", "",
        f"- Accessibility readiness: **{report.accessibility_status}**",
        f"- Performance readiness: **{report.performance_status}**", "",
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


@router.get("/projects/{project_id}/reports", response_model=list[ReportHistoryResponse])
async def list_project_reports(
    project_id: str,
    db: AsyncSession = Depends(get_db_session),
) -> list[ReportHistoryResponse]:
    if not await db.get(Project, project_id):
        raise HTTPException(status_code=404, detail="Project not found")
    reports = (await db.execute(
        select(Report)
        .join(ScanSession, Report.scan_id == ScanSession.id)
        .where(ScanSession.project_id == project_id)
        .order_by(Report.created_at.desc())
    )).scalars().all()
    return [
        ReportHistoryResponse(id=report.id, scan_id=report.scan_id, format=report.format or "unknown", created_at=report.created_at)
        for report in reports
    ]


@router.post("/scans/{scan_id}/baseline", response_model=ScanReportResponse)
async def create_baseline(scan_id: str, db: AsyncSession = Depends(get_db_session)) -> ScanReportResponse:
    scan = await db.get(ScanSession, scan_id)
    if not scan:
        raise HTTPException(status_code=404, detail="Scan session not found")
    findings = (await db.execute(select(Finding).where(Finding.scan_id == scan_id))).scalars().all()
    db.add(Baseline(id=str(uuid4()), project_id=scan.project_id, fingerprints=[finding.fingerprint for finding in findings]))
    await db.commit()
    return await scan_report(scan_id, db)
