from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_session
from app.models import (BehaviorCoverageRecord, Finding, GeneratedTestCase, ManualTestCase,
                        Project, ScanSession, TestRun)
from app.schemas.behavior_coverage import BehaviorCoverageResponse, BehaviorCoverageSummary
from app.services.behavior_coverage import (coverage_fingerprint, coverage_from_generated,
                                            coverage_from_manual, coverage_from_test_run)
from app.services.findings import complete_finding

router = APIRouter()


@router.post("/projects/{project_id}/behavior-coverage/derive", response_model=BehaviorCoverageSummary)
async def derive_behavior_coverage(project_id: str, scan_id: str | None = Query(default=None),
                                   db: AsyncSession = Depends(get_db_session)) -> BehaviorCoverageSummary:
    if not await db.get(Project, project_id):
        raise HTTPException(404, "Project not found")
    scan = await db.get(ScanSession, scan_id) if scan_id else None
    if scan_id and (not scan or scan.project_id != project_id):
        raise HTTPException(422, "Scan does not belong to the selected project")
    generated = list((await db.execute(select(GeneratedTestCase).where(
        GeneratedTestCase.project_id == project_id))).scalars().all())
    manual = list((await db.execute(select(ManualTestCase).where(
        ManualTestCase.project_id == project_id))).scalars().all())
    runs = list((await db.execute(select(TestRun).where(TestRun.scan_id == scan_id))).scalars().all()) if scan_id else []
    candidates = [coverage_from_generated(item) for item in generated]
    candidates += [coverage_from_manual(item) for item in manual]
    candidates += [coverage_from_test_run(item) for item in runs]
    rows: list[BehaviorCoverageRecord] = []
    for candidate in candidates:
        fingerprint = coverage_fingerprint(project_id, candidate["capability_key"])
        record = (await db.execute(select(BehaviorCoverageRecord).where(
            BehaviorCoverageRecord.fingerprint == fingerprint))).scalars().first()
        if not record:
            record = BehaviorCoverageRecord(id=str(uuid4()), project_id=project_id, fingerprint=fingerprint, **candidate)
            db.add(record)
        else:
            for key, value in candidate.items():
                setattr(record, key, value)
        record.scan_id = scan_id
        rows.append(record)
        if scan_id and candidate["coverage_status"] == "UNTESTED" and candidate["criticality"] in {"HIGH", "CRITICAL"}:
            finding_fingerprint = coverage_fingerprint(scan_id, "gap:" + candidate["capability_key"])
            existing = (await db.execute(select(Finding).where(
                Finding.scan_id == scan_id, Finding.fingerprint == finding_fingerprint))).scalars().first()
            if not existing:
                finding = complete_finding({"id": str(uuid4()), "scan_id": scan_id,
                    "title": "Important behavior lacks executed test evidence", "severity": "MEDIUM",
                    "tool": "qsscope-behavior", "stage": "BEHAVIOR_COVERAGE", "category": "TESTS",
                    "subcategory": "BEHAVIOR_GAP", "message": candidate["title"],
                    "evidence": candidate["evidence"], "fingerprint": finding_fingerprint, "status": "OPEN"})
                db.add(Finding(**finding))
    await db.commit()
    for row in rows:
        await db.refresh(row)
    return BehaviorCoverageSummary(total=len(rows), covered=sum(row.coverage_status == "COVERED" for row in rows),
        partially_covered=sum(row.coverage_status == "PARTIALLY_COVERED" for row in rows),
        untested=sum(row.coverage_status == "UNTESTED" for row in rows),
        unknown=sum(row.coverage_status == "UNKNOWN" for row in rows), records=rows)


@router.get("/projects/{project_id}/behavior-coverage", response_model=list[BehaviorCoverageResponse])
async def list_behavior_coverage(project_id: str, db: AsyncSession = Depends(get_db_session)) -> list[BehaviorCoverageRecord]:
    return list((await db.execute(select(BehaviorCoverageRecord).where(
        BehaviorCoverageRecord.project_id == project_id).order_by(BehaviorCoverageRecord.criticality,
                                                                    BehaviorCoverageRecord.title))).scalars().all())
