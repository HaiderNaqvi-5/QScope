"""Normalized native-test evidence endpoints."""
from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_session
from app.models import TestRun

router = APIRouter()


@router.get("/scans/{scan_id}/test-runs")
async def test_runs(scan_id: str, db: AsyncSession = Depends(get_db_session)) -> list[dict]:
    rows = (await db.execute(select(TestRun).where(TestRun.scan_id == scan_id)
                             .order_by(TestRun.created_at, TestRun.id))).scalars().all()
    return [{"id": row.id, "scan_id": row.scan_id, "task_id": row.task_id, "suite_name": row.suite_name,
             "framework": row.framework, "discovered": row.discovered, "passed": row.passed, "failed": row.failed,
             "skipped": row.skipped, "duration_ms": row.duration_ms, "coverage_percent": row.coverage_percent,
             "status": row.status, "raw_artifact_id": row.raw_artifact_id, "details": row.details} for row in rows]
