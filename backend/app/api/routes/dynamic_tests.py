import hashlib
from uuid import uuid4

import httpx
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_session
from app.models import Finding, GeneratedTestCase, Project, ScanSession
from app.schemas.dynamic_tests import ConcurrencyRunRequest, ResilienceRunRequest
from app.schemas.generated_tests import GeneratedTestRunResponse
from app.services.dynamic_testing import run_concurrency_probe, run_resilience_probe
from app.services.findings import complete_finding

router = APIRouter()


async def _context(project_id: str, scan_id: str | None, db: AsyncSession) -> tuple[Project, ScanSession | None]:
    project = await db.get(Project, project_id)
    if not project:
        raise HTTPException(404, "Project not found")
    scan = await db.get(ScanSession, scan_id) if scan_id else None
    if scan_id and (not scan or scan.project_id != project_id):
        raise HTTPException(422, "Scan does not belong to the selected project")
    return project, scan


async def _persist_case(db: AsyncSession, project_id: str, scan_id: str | None, category: str,
                        method: str, endpoint: str, title: str, outcome: dict, source: str) -> GeneratedTestCase:
    fingerprint = hashlib.sha256(f"{project_id}|{category}|{method}|{endpoint}|{title}".encode()).hexdigest()
    case = (await db.execute(select(GeneratedTestCase).where(
        GeneratedTestCase.fingerprint == fingerprint))).scalars().first()
    if not case:
        case = GeneratedTestCase(id=str(uuid4()), project_id=project_id, category=category, title=title,
            method=method, endpoint=endpoint, actor="configured-local-actor", input_data={},
            expected={"status": "PASSED"}, source_path=source, fingerprint=fingerprint)
        db.add(case)
    case.scan_id = scan_id
    case.status = outcome["status"]
    case.evidence = outcome["evidence"]
    if outcome["status"] == "FAILED" and scan_id:
        finding_fingerprint = hashlib.sha256(f"dynamic|{fingerprint}".encode()).hexdigest()
        existing = (await db.execute(select(Finding).where(
            Finding.scan_id == scan_id, Finding.fingerprint == finding_fingerprint))).scalars().first()
        if not existing:
            finding = complete_finding({"id": str(uuid4()), "scan_id": scan_id, "title": title,
                "severity": "HIGH", "tool": "qsscope-dynamic", "stage": category,
                "category": "API_RELIABILITY", "subcategory": category,
                "endpoint": f"{method} {endpoint}", "message": f"Controlled {category.lower()} scenario failed.",
                "evidence": outcome["evidence"], "fingerprint": finding_fingerprint, "status": "OPEN"})
            db.add(Finding(**finding))
    return case


@router.post("/projects/{project_id}/concurrency/run", response_model=GeneratedTestRunResponse)
async def concurrency(project_id: str, request: ConcurrencyRunRequest,
                      db: AsyncSession = Depends(get_db_session)) -> GeneratedTestRunResponse:
    await _context(project_id, request.scan_id, db)
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(10, connect=3), follow_redirects=False) as client:
            outcome = await run_concurrency_probe(client, request.model_dump())
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    case = await _persist_case(db, project_id, request.scan_id, "CONCURRENCY", request.method,
                               request.endpoint, f"Limited concurrency: {request.method} {request.endpoint}",
                               outcome, "configured-runtime")
    await db.commit(); await db.refresh(case)
    return GeneratedTestRunResponse(total=1, passed=int(case.status == "PASSED"), failed=int(case.status == "FAILED"),
                                    blocked=int(case.status == "BLOCKED"), results=[case])


@router.post("/projects/{project_id}/resilience/run", response_model=GeneratedTestRunResponse)
async def resilience(project_id: str, request: ResilienceRunRequest,
                     db: AsyncSession = Depends(get_db_session)) -> GeneratedTestRunResponse:
    await _context(project_id, request.scan_id, db)
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(10, connect=3), follow_redirects=False) as client:
            outcomes = await run_resilience_probe(client, request.model_dump())
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    rows = [await _persist_case(db, project_id, request.scan_id, "RESILIENCE", request.method,
            request.endpoint, f"Controlled resilience ({outcome['kind']}): {request.method} {request.endpoint}",
            outcome, "configured-runtime") for outcome in outcomes]
    await db.commit()
    for row in rows: await db.refresh(row)
    return GeneratedTestRunResponse(total=len(rows), passed=sum(row.status == "PASSED" for row in rows),
                                    failed=sum(row.status == "FAILED" for row in rows),
                                    blocked=sum(row.status == "BLOCKED" for row in rows), results=rows)
