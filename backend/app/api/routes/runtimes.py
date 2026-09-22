"""Per-project local runtime profile endpoints."""
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_session
from app.models import Project, RuntimeProfile
from app.schemas.runtime_profiles import RuntimeLogResponse, RuntimeProfileCreate, RuntimeProfileResponse, RuntimeStartRequest
from app.services.runtime_manager import runtime_log, start_runtime, stop_runtime, validate_local_url, resolve_project_path

router = APIRouter()


@router.post("/projects/{project_id}/runtime-profiles", response_model=RuntimeProfileResponse, status_code=201)
async def create_runtime_profile(project_id: str, request: RuntimeProfileCreate,
                                 db: AsyncSession = Depends(get_db_session)) -> RuntimeProfile:
    project = await db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    try:
        validate_local_url(request.local_url)
        if request.health_endpoint and "://" in request.health_endpoint:
            validate_local_url(request.health_endpoint)
        resolve_project_path(Path(project.root_path), request.working_directory, require_dir=True)
        if request.environment_file:
            resolve_project_path(Path(project.root_path), request.environment_file)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    profile = RuntimeProfile(id=str(uuid4()), project_id=project_id, **request.model_dump())
    db.add(profile)
    await db.commit()
    await db.refresh(profile)
    return profile


@router.get("/projects/{project_id}/runtime-profiles", response_model=list[RuntimeProfileResponse])
async def list_runtime_profiles(project_id: str, db: AsyncSession = Depends(get_db_session)) -> list[RuntimeProfile]:
    if not await db.get(Project, project_id):
        raise HTTPException(status_code=404, detail="Project not found")
    return list((await db.execute(select(RuntimeProfile).where(RuntimeProfile.project_id == project_id)
                                  .order_by(RuntimeProfile.created_at))).scalars().all())


@router.post("/runtime-profiles/{profile_id}/start", response_model=RuntimeProfileResponse)
async def launch_runtime(profile_id: str, request: RuntimeStartRequest,
                         db: AsyncSession = Depends(get_db_session)) -> RuntimeProfile:
    profile = await db.get(RuntimeProfile, profile_id)
    if not profile:
        raise HTTPException(status_code=404, detail="Runtime profile not found")
    project = await db.get(Project, profile.project_id)
    try:
        await start_runtime(profile, Path(project.root_path), approved=request.approved)
    except PermissionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except (ValueError, RuntimeError, TimeoutError, OSError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    await db.refresh(profile)
    return profile


@router.post("/runtime-profiles/{profile_id}/stop", response_model=RuntimeProfileResponse)
async def halt_runtime(profile_id: str, db: AsyncSession = Depends(get_db_session)) -> RuntimeProfile:
    profile = await db.get(RuntimeProfile, profile_id)
    if not profile:
        raise HTTPException(status_code=404, detail="Runtime profile not found")
    await stop_runtime(profile_id)
    await db.refresh(profile)
    return profile


@router.get("/runtime-profiles/{profile_id}/logs", response_model=RuntimeLogResponse)
async def runtime_logs(profile_id: str, db: AsyncSession = Depends(get_db_session)) -> RuntimeLogResponse:
    if not await db.get(RuntimeProfile, profile_id):
        raise HTTPException(status_code=404, detail="Runtime profile not found")
    output, truncated = runtime_log(profile_id)
    return RuntimeLogResponse(profile_id=profile_id, output=output, truncated=truncated)
