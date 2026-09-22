"""Mutation/test-strength API."""
import hashlib
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_session
from app.models import GeneratedTestCase, Project, ScanSession
from app.schemas.mutation import MutationRunRequest, MutationRunResponse
from app.services.mutation_testing import run_mutation_analysis

router = APIRouter()


@router.post("/projects/{project_id}/mutation/run", response_model=MutationRunResponse)
async def run_mutation(project_id: str, request: MutationRunRequest,
                       db: AsyncSession = Depends(get_db_session)) -> MutationRunResponse:
    project = await db.get(Project, project_id)
    if not project:
        raise HTTPException(404, "Project not found")
    if request.scan_id:
        scan = await db.get(ScanSession, request.scan_id)
        if not scan or scan.project_id != project_id:
            raise HTTPException(404, "Scan session not found for project")
    result = await run_mutation_analysis(Path(project.root_path).resolve(), request.engine,
                                         request.timeout_seconds)
    case_status = result["status"]
    if case_status == "COMPLETED":
        case_status = "FAILED" if result.get("survived") else "PASSED"
    db.add(GeneratedTestCase(
        id=str(uuid4()), project_id=project_id, scan_id=request.scan_id, category="MUTATION",
        title=f"{result.get('engine') or 'Unsupported'} mutation test strength",
        method="TEST", endpoint="mutation://project", actor=None, input_data={"engine": request.engine},
        expected={"behavior": "Mutation score distinguishes test strength from coverage"},
        status=case_status, evidence={key: value for key, value in result.items() if key != "message"},
        source_path=".", fingerprint=hashlib.sha256(
            f"{project_id}|mutation|{request.scan_id or 'project'}|{result.get('engine')}".encode()).hexdigest(),
    ))
    await db.commit()
    return MutationRunResponse(project_id=project_id, scan_id=request.scan_id, **result)
