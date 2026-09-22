from pathlib import Path
from uuid import uuid4
import hashlib
import httpx

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_session
from app.models import Finding, GeneratedTestCase, Project, ScanSession
from app.schemas.generated_tests import (GeneratedTestCaseResponse, GeneratedTestRunRequest,
                                         GeneratedTestRunResponse, GenerationResponse,
                                         DataIntegrityRunRequest)
from app.services.schema_testing import (derive_schema_cases, execute_generated_case, load_openapi,
                                         validate_loopback_base_url)
from app.services.findings import complete_finding
from app.services.data_integrity import inspect_sqlite_read_only

router = APIRouter()


@router.post("/projects/{project_id}/generated-tests/derive", response_model=GenerationResponse)
async def derive_tests(project_id: str, db: AsyncSession = Depends(get_db_session)) -> GenerationResponse:
    project = await db.get(Project, project_id)
    if not project:
        raise HTTPException(404, "Project not found")
    root = Path(project.root_path).resolve()
    spec_paths = sorted({path for item in (project.project_model or {}).get("api_specs", [])
                         for path in item.get("evidence", [])})
    if not spec_paths:
        raise HTTPException(409, "No OpenAPI specification was detected")
    existing = set((await db.execute(select(GeneratedTestCase.fingerprint).where(
        GeneratedTestCase.project_id == project_id))).scalars().all())
    generated = 0
    for relative in spec_paths:
        path = (root / relative).resolve()
        if root not in path.parents or not path.is_file():
            raise HTTPException(422, "OpenAPI evidence path is unsafe or missing")
        try:
            cases = derive_schema_cases(load_openapi(path), relative)
        except (OSError, ValueError) as exc:
            raise HTTPException(422, f"OpenAPI specification could not be parsed: {exc}") from exc
        for case in cases:
            case["fingerprint"] = hashlib.sha256(
                f"{project_id}|{case['fingerprint']}".encode()
            ).hexdigest()
            if case["fingerprint"] not in existing:
                db.add(GeneratedTestCase(id=str(uuid4()), project_id=project_id, **case))
                existing.add(case["fingerprint"])
                generated += 1
    await db.commit()
    rows = list((await db.execute(select(GeneratedTestCase).where(
        GeneratedTestCase.project_id == project_id).order_by(GeneratedTestCase.category, GeneratedTestCase.endpoint,
                                                               GeneratedTestCase.title))).scalars().all())
    return GenerationResponse(project_id=project_id, generated=generated, total=len(rows), cases=rows)


@router.get("/projects/{project_id}/generated-tests", response_model=list[GeneratedTestCaseResponse])
async def list_generated_tests(project_id: str, category: str | None = Query(
    default=None, pattern="^(CONTRACT|LOGICAL|EDGE|DATA_INTEGRITY|CONCURRENCY|RESILIENCE|MUTATION)$"),
                               db: AsyncSession = Depends(get_db_session)) -> list[GeneratedTestCase]:
    if not await db.get(Project, project_id):
        raise HTTPException(404, "Project not found")
    statement = select(GeneratedTestCase).where(GeneratedTestCase.project_id == project_id)
    if category:
        statement = statement.where(GeneratedTestCase.category == category)
    return list((await db.execute(statement.order_by(GeneratedTestCase.category, GeneratedTestCase.endpoint,
                                                      GeneratedTestCase.title))).scalars().all())


@router.post("/projects/{project_id}/generated-tests/run", response_model=GeneratedTestRunResponse)
async def run_generated_tests(project_id: str, request: GeneratedTestRunRequest,
                              db: AsyncSession = Depends(get_db_session)) -> GeneratedTestRunResponse:
    if not await db.get(Project, project_id):
        raise HTTPException(404, "Project not found")
    scan = await db.get(ScanSession, request.scan_id) if request.scan_id else None
    if request.scan_id and (not scan or scan.project_id != project_id):
        raise HTTPException(422, "Scan does not belong to the selected project")
    try:
        base_url = validate_loopback_base_url(request.base_url)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    statement = select(GeneratedTestCase).where(GeneratedTestCase.project_id == project_id)
    if request.case_ids:
        statement = statement.where(GeneratedTestCase.id.in_(request.case_ids))
    cases = list((await db.execute(statement.order_by(GeneratedTestCase.category, GeneratedTestCase.endpoint,
                                                       GeneratedTestCase.title))).scalars().all())
    if not cases:
        raise HTTPException(409, "No generated tests are available for execution")
    safe_headers = {key: value for key, value in request.actor_headers.items()
                    if key.lower() not in {"host", "content-length", "connection"}}
    async with httpx.AsyncClient(timeout=httpx.Timeout(10, connect=3), follow_redirects=False) as client:
        for case in cases:
            result = await execute_generated_case(client, base_url, {
                "category": case.category, "method": case.method, "endpoint": case.endpoint,
                "actor": case.actor, "input_data": case.input_data or {}, "expected": case.expected or {},
                "evidence": case.evidence or {},
            }, safe_headers, request.actor_profiles)
            case.status = result["status"]
            case.scan_id = request.scan_id
            case.evidence = {**(case.evidence or {}), "execution": result["evidence"]}
            if case.status == "FAILED" and request.scan_id:
                fingerprint = hashlib.sha256(f"generated-test|{case.fingerprint}".encode()).hexdigest()
                existing = (await db.execute(select(Finding).where(
                    Finding.scan_id == request.scan_id, Finding.fingerprint == fingerprint))).scalars().first()
                if not existing:
                    finding = complete_finding({
                        "id": str(uuid4()), "scan_id": request.scan_id,
                        "title": f"{case.category.title()} scenario failed: {case.method} {case.endpoint}",
                        "severity": "HIGH" if case.category == "LOGICAL" else "MEDIUM",
                        "tool": "qsscope-schema", "stage": f"{case.category}_TESTING",
                        "category": "SECURITY" if case.category == "LOGICAL" else "API_RELIABILITY",
                        "subcategory": "AUTHORIZATION" if case.category == "LOGICAL" else case.category,
                        "endpoint": f"{case.method} {case.endpoint}",
                        "message": f"Expected {case.expected.get('status_codes', [])}; observed {result['evidence'].get('actual_status')}",
                        "evidence": {"generated_test_id": case.id, **result["evidence"]},
                        "fingerprint": fingerprint, "status": "OPEN",
                    })
                    db.add(Finding(**finding))
    await db.commit()
    for case in cases:
        await db.refresh(case)
    return GeneratedTestRunResponse(total=len(cases), passed=sum(case.status == "PASSED" for case in cases),
                                    failed=sum(case.status == "FAILED" for case in cases),
                                    blocked=sum(case.status in {"BLOCKED", "NOT_APPLICABLE"} for case in cases),
                                    results=cases)


@router.post("/projects/{project_id}/data-integrity/run", response_model=GeneratedTestRunResponse)
async def run_data_integrity(project_id: str, request: DataIntegrityRunRequest,
                             db: AsyncSession = Depends(get_db_session)) -> GeneratedTestRunResponse:
    project = await db.get(Project, project_id)
    if not project:
        raise HTTPException(404, "Project not found")
    scan = await db.get(ScanSession, request.scan_id) if request.scan_id else None
    if request.scan_id and (not scan or scan.project_id != project_id):
        raise HTTPException(422, "Scan does not belong to the selected project")
    try:
        checks = inspect_sqlite_read_only(Path(project.root_path), request.database_path)
    except (OSError, ValueError) as exc:
        raise HTTPException(422, str(exc)) from exc
    rows: list[GeneratedTestCase] = []
    for check in checks:
        fingerprint = hashlib.sha256(f"{project_id}|data-integrity|{request.database_path}|{check['name']}".encode()).hexdigest()
        case = (await db.execute(select(GeneratedTestCase).where(
            GeneratedTestCase.fingerprint == fingerprint))).scalars().first()
        if not case:
            case = GeneratedTestCase(id=str(uuid4()), project_id=project_id, category="DATA_INTEGRITY",
                title=check["name"], method="READ_ONLY_SQL", endpoint=request.database_path, actor="qsscope",
                input_data={}, expected={"status": "PASSED"}, source_path=request.database_path,
                fingerprint=fingerprint)
            db.add(case)
        case.scan_id = request.scan_id
        case.status = check["status"]
        case.evidence = check["evidence"]
        rows.append(case)
        if check["status"] == "FAILED" and request.scan_id:
            finding_fingerprint = hashlib.sha256(f"data-integrity|{fingerprint}".encode()).hexdigest()
            existing = (await db.execute(select(Finding).where(
                Finding.scan_id == request.scan_id, Finding.fingerprint == finding_fingerprint))).scalars().first()
            if not existing:
                finding = complete_finding({"id": str(uuid4()), "scan_id": request.scan_id,
                    "title": check["name"], "severity": check["severity"], "tool": "qsscope-sqlite",
                    "stage": "DATA_INTEGRITY", "category": "API_RELIABILITY", "subcategory": "DATA_INTEGRITY",
                    "message": f"Read-only database check failed for {request.database_path}.",
                    "evidence": check["evidence"], "fingerprint": finding_fingerprint, "status": "OPEN"})
                db.add(Finding(**finding))
    await db.commit()
    for row in rows:
        await db.refresh(row)
    return GeneratedTestRunResponse(total=len(rows), passed=sum(row.status == "PASSED" for row in rows),
                                    failed=sum(row.status == "FAILED" for row in rows), blocked=0, results=rows)
