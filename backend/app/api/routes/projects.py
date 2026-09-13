"""Project discovery and scan-plan endpoints."""
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_session
from app.models import Project
from app.schemas.projects import ProjectDiscoverRequest, ProjectResponse, ProjectModel, ScanPlanResponse
from app.services.discovery import discover_project
from app.services.preflight import build_scan_plan

router = APIRouter()


def _response(project: Project) -> ProjectResponse:
    return ProjectResponse(
        id=project.id, name=project.name, root_path=project.root_path,
        model=ProjectModel.model_validate(project.project_model),
    )


@router.post("/projects/discover", response_model=ProjectResponse)
async def discover(request: ProjectDiscoverRequest, db: AsyncSession = Depends(get_db_session)) -> ProjectResponse:
    try:
        root, model = discover_project(request.root_path)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    existing = (await db.execute(select(Project).where(Project.root_path == str(root)))).scalar_one_or_none()
    if existing:
        existing.name, existing.project_model = root.name or str(root), model
        project = existing
    else:
        project = Project(id=str(uuid4()), name=root.name or str(root), root_path=str(root), project_model=model)
        db.add(project)
    await db.commit()
    await db.refresh(project)
    return _response(project)


@router.get("/projects", response_model=list[ProjectResponse])
async def list_projects(db: AsyncSession = Depends(get_db_session)) -> list[ProjectResponse]:
    projects = (await db.execute(select(Project).order_by(Project.updated_at.desc()))).scalars().all()
    return [_response(project) for project in projects]


@router.get("/projects/{project_id}/scan-plan", response_model=ScanPlanResponse)
async def scan_plan(
    project_id: str,
    mode: str = Query("STANDARD", pattern="^(QUICK|STANDARD|FULL)$"),
    db: AsyncSession = Depends(get_db_session),
) -> ScanPlanResponse:
    project = await db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    tools, tasks = build_scan_plan(project.id, project.project_model, mode)
    return ScanPlanResponse(project_id=project.id, mode=mode, tools=tools, tasks=tasks)
