"""Project discovery and scan-plan endpoints."""
from pathlib import Path
import time
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
import httpx
import json
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_session
from app.models import Project
from app.schemas.projects import (
    ProjectDiscoverRequest,
    ProjectResponse,
    ProjectModel,
    RuntimeHealthResponse,
    RuntimeTarget,
    ScanPlanResponse,
)
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


@router.post("/projects/{project_id}/runtime-target", response_model=ProjectResponse)
async def configure_runtime_target(
    project_id: str,
    target: RuntimeTarget,
    db: AsyncSession = Depends(get_db_session),
) -> ProjectResponse:
    project = await db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    model = dict(project.project_model or {})
    model["runtime_targets"] = [{
        "host": target.host,
        "port": target.port,
        "scheme": target.scheme,
        "base_url": target.base_url,
    }]
    project.project_model = model
    await db.commit()
    await db.refresh(project)
    return _response(project)


@router.get("/projects/{project_id}/runtime-target/health", response_model=RuntimeHealthResponse)
async def runtime_target_health(
    project_id: str,
    db: AsyncSession = Depends(get_db_session),
) -> RuntimeHealthResponse:
    project = await db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    targets = (project.project_model or {}).get("runtime_targets", [])
    if not targets or not targets[0].get("base_url"):
        return RuntimeHealthResponse(status="NOT_CONFIGURED")
    target = str(targets[0]["base_url"])
    started = time.monotonic()
    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(3.0, connect=1.0),
            follow_redirects=False,
        ) as client:
            response = await client.get(target)
    except (httpx.TimeoutException, httpx.NetworkError) as exc:
        return RuntimeHealthResponse(
            status="UNREACHABLE",
            target=target,
            latency_ms=int((time.monotonic() - started) * 1000),
            error=exc.__class__.__name__,
        )
    return RuntimeHealthResponse(
        status="HEALTHY" if response.is_success or response.is_redirect else "UNHEALTHY",
        target=target,
        status_code=response.status_code,
        latency_ms=int((time.monotonic() - started) * 1000),
    )


@router.get("/projects/{project_id}/dependencies/export")
async def export_dependencies(
    project_id: str,
    format: str = Query("cyclonedx", pattern="^cyclonedx$"),
    db: AsyncSession = Depends(get_db_session),
) -> Response:
    project = await db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    dependencies = (project.project_model or {}).get("dependencies", [])
    components = []
    for dependency in sorted(
        dependencies,
        key=lambda item: (str(item.get("name", "")), str(item.get("version", "")), str(item.get("manifest", ""))),
    ):
        name = str(dependency.get("name", "unknown"))
        version = str(dependency.get("version", "*"))
        manifest = str(dependency.get("manifest", "unknown"))
        ecosystem = "npm" if manifest in {"package.json", "package-lock.json", "npm-shrinkwrap.json"} else "pypi"
        components.append({
            "type": "library",
            "name": name,
            "version": version,
            "scope": "optional",
            "purl": f"pkg:{ecosystem}/{name}@{version}",
            "properties": [{"name": "qsscope:manifest", "value": manifest}],
            "licenses": [{"license": {"name": "UNKNOWN"}}],
        })
    body = json.dumps({
        "bomFormat": "CycloneDX",
        "specVersion": "1.5",
        "version": 1,
        "metadata": {"component": {"type": "application", "name": project.name}},
        "components": components,
    }, indent=2, sort_keys=True)
    return Response(body, media_type="application/json", headers={
        "Content-Disposition": f'attachment; filename="qsscope-{project_id}-sbom.json"',
    })
