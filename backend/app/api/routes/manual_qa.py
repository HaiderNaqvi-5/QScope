"""Manual test case and evidence endpoints."""
from __future__ import annotations

import hashlib
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_session
from app.core.paths import get_data_dir, is_path_safe
from app.models import ManualTestCase, ManualTestEvidence, Project
from app.schemas.manual_qa import ManualEvidenceResponse, ManualTestCreate, ManualTestResponse, ManualTestUpdate

router = APIRouter()
MAX_EVIDENCE_BYTES = 10 * 1024 * 1024
ALLOWED_EVIDENCE_TYPES = {"image/png", "image/jpeg", "image/webp", "text/plain", "application/pdf"}


def _checklist(project: Project) -> list[dict]:
    model = project.project_model or {}
    cases = [{"module": "Release validation", "feature": "Critical user journey",
              "preconditions": ["Use a local disposable test environment"],
              "steps": ["Complete the primary user workflow", "Verify success and error feedback"],
              "expected_result": "The workflow completes with clear, accurate feedback and no data loss."}]
    if model.get("frontend_targets"):
        cases.extend([
            {"module": "Accessibility", "feature": "Keyboard navigation",
             "preconditions": ["Open the primary page at desktop width"],
             "steps": ["Navigate all interactive controls using Tab and Shift+Tab", "Activate controls using the keyboard"],
             "expected_result": "Focus order is logical, every control is reachable, and focus remains visible."},
            {"module": "Accessibility", "feature": "Screen-reader semantics",
             "preconditions": ["Enable a screen reader or accessibility tree inspector"],
             "steps": ["Review headings, landmarks, names, roles, values, and validation messages"],
             "expected_result": "Content structure and control purpose are announced accurately."},
            {"module": "Responsive UX", "feature": "Mobile navigation and actions",
             "preconditions": ["Set viewport to 320×568"],
             "steps": ["Navigate the primary route", "Inspect menus, dialogs, forms, and critical actions"],
             "expected_result": "No essential navigation/action is hidden, clipped, overlapped, or unusable."},
        ])
    return cases


@router.post("/projects/{project_id}/manual-tests/derive", response_model=list[ManualTestResponse])
async def derive_manual_tests(project_id: str,
                              db: AsyncSession = Depends(get_db_session)) -> list[ManualTestResponse]:
    project = await db.get(Project, project_id)
    if not project:
        raise HTTPException(404, "Project not found")
    existing = {(item.module, item.feature): item for item in (await db.execute(select(ManualTestCase).where(
        ManualTestCase.project_id == project_id,
        ManualTestCase.source == "DETERMINISTIC_GENERATED_DRAFT"))).scalars().all()}
    rows: list[ManualTestCase] = []
    for candidate in _checklist(project):
        key = (candidate["module"], candidate["feature"])
        case = existing.get(key)
        if not case:
            case = ManualTestCase(id=str(uuid4()), project_id=project_id, status="NOT_RUN", severity=None,
                                  actual_result=None, notes=None, source="DETERMINISTIC_GENERATED_DRAFT",
                                  accepted=False, **candidate)
            db.add(case)
        rows.append(case)
    await db.commit()
    for row in rows:
        await db.refresh(row)
    return [await _response(row, db) for row in rows]


async def _response(case: ManualTestCase, db: AsyncSession) -> ManualTestResponse:
    evidence = list((await db.execute(select(ManualTestEvidence).where(
        ManualTestEvidence.test_id == case.id).order_by(ManualTestEvidence.created_at))).scalars().all())
    return ManualTestResponse.model_validate(case, from_attributes=True).model_copy(update={
        "evidence": [ManualEvidenceResponse.model_validate(item, from_attributes=True) for item in evidence]
    })


@router.get("/projects/{project_id}/manual-tests", response_model=list[ManualTestResponse])
async def list_manual_tests(project_id: str, db: AsyncSession = Depends(get_db_session)) -> list[ManualTestResponse]:
    if not await db.get(Project, project_id):
        raise HTTPException(404, "Project not found")
    cases = (await db.execute(select(ManualTestCase).where(ManualTestCase.project_id == project_id)
                              .order_by(ManualTestCase.created_at))).scalars().all()
    return [await _response(case, db) for case in cases]


@router.post("/manual-tests", response_model=ManualTestResponse, status_code=201)
async def create_manual_test(request: ManualTestCreate,
                             db: AsyncSession = Depends(get_db_session)) -> ManualTestResponse:
    if not await db.get(Project, request.project_id):
        raise HTTPException(404, "Project not found")
    case = ManualTestCase(id=str(uuid4()), source="MANUAL", accepted=True, **request.model_dump())
    db.add(case)
    await db.commit(); await db.refresh(case)
    return await _response(case, db)


@router.patch("/manual-tests/{test_id}", response_model=ManualTestResponse)
async def update_manual_test(test_id: str, request: ManualTestUpdate,
                             db: AsyncSession = Depends(get_db_session)) -> ManualTestResponse:
    case = await db.get(ManualTestCase, test_id)
    if not case:
        raise HTTPException(404, "Manual test not found")
    values = request.model_dump(exclude_unset=True)
    next_status = values.get("status", case.status)
    next_severity = values.get("severity", case.severity)
    if next_status == "FAIL" and not next_severity:
        raise HTTPException(422, "Failed manual tests require severity")
    for key, value in values.items():
        setattr(case, key, value)
    await db.commit(); await db.refresh(case)
    return await _response(case, db)


@router.delete("/manual-tests/{test_id}", status_code=204)
async def delete_manual_test(test_id: str, db: AsyncSession = Depends(get_db_session)) -> None:
    case = await db.get(ManualTestCase, test_id)
    if not case:
        raise HTTPException(404, "Manual test not found")
    evidence = (await db.execute(select(ManualTestEvidence).where(ManualTestEvidence.test_id == test_id))).scalars().all()
    data_root = get_data_dir().resolve()
    for item in evidence:
        path = data_root / item.relative_path
        if is_path_safe(path, data_root) and path.is_file():
            path.unlink()
    await db.execute(delete(ManualTestEvidence).where(ManualTestEvidence.test_id == test_id))
    await db.delete(case); await db.commit()


@router.post("/manual-tests/{test_id}/evidence", response_model=ManualEvidenceResponse, status_code=201)
async def attach_manual_evidence(test_id: str, file: UploadFile = File(...),
                                 db: AsyncSession = Depends(get_db_session)) -> ManualTestEvidence:
    case = await db.get(ManualTestCase, test_id)
    if not case:
        raise HTTPException(404, "Manual test not found")
    mime_type = file.content_type or "application/octet-stream"
    if mime_type not in ALLOWED_EVIDENCE_TYPES:
        raise HTTPException(422, "Unsupported evidence type")
    content = await file.read(MAX_EVIDENCE_BYTES + 1)
    if len(content) > MAX_EVIDENCE_BYTES:
        raise HTTPException(413, "Evidence exceeds the 10 MiB limit")
    suffix = {"image/png": ".png", "image/jpeg": ".jpg", "image/webp": ".webp",
              "text/plain": ".txt", "application/pdf": ".pdf"}[mime_type]
    data_root = get_data_dir().resolve()
    directory = data_root / "projects" / case.project_id / "manual-evidence" / case.id
    directory.mkdir(parents=True, exist_ok=True)
    evidence_id = str(uuid4())
    path = directory / f"{evidence_id}{suffix}"
    if not is_path_safe(path, data_root):
        raise HTTPException(422, "Evidence path is unsafe")
    path.write_bytes(content)
    evidence = ManualTestEvidence(id=evidence_id, test_id=test_id,
        relative_path=path.relative_to(data_root).as_posix(), sha256=hashlib.sha256(content).hexdigest(),
        mime_type=mime_type, original_name=Path(file.filename or "evidence").name[:512])
    db.add(evidence); await db.commit(); await db.refresh(evidence)
    return evidence


@router.get("/manual-evidence/{evidence_id}", response_class=FileResponse)
async def download_manual_evidence(evidence_id: str, db: AsyncSession = Depends(get_db_session)) -> FileResponse:
    evidence = await db.get(ManualTestEvidence, evidence_id)
    if not evidence:
        raise HTTPException(404, "Manual evidence not found")
    data_root = get_data_dir().resolve()
    path = (data_root / evidence.relative_path).resolve()
    if not is_path_safe(path, data_root) or not path.is_file():
        raise HTTPException(404, "Manual evidence file not found")
    return FileResponse(path, media_type=evidence.mime_type, filename=evidence.original_name)
