"""Local analyzer readiness endpoints."""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_session
from app.models import Project
from app.schemas.projects import ToolStatus
from app.services.preflight import inspect_tools

router = APIRouter()


def _all_capabilities_model() -> dict:
    return {
        "languages": [{"value": value} for value in ("Python", "JavaScript", "TypeScript", "Java", "PHP", "Go", "C#", "Rust")],
        "docker": {"detected": True}, "api_specs": [{}], "graphql_specs": [{}], "postman_collections": [{}],
        "browser_tests": [{}], "accessibility_tests": [{}], "performance_tests": [{}], "security_tests": [{}],
        "load_tests": [{"value": "k6"}],
    }


async def _statuses(project_id: str | None, db: AsyncSession) -> list[ToolStatus]:
    if project_id:
        project = await db.get(Project, project_id)
        if not project:
            raise HTTPException(404, "Project not found")
        return inspect_tools(project.project_model or {})
    return inspect_tools(_all_capabilities_model())


@router.get("/tooling/status", response_model=list[ToolStatus])
async def tooling_status(project_id: str | None = Query(None),
                         db: AsyncSession = Depends(get_db_session)) -> list[ToolStatus]:
    return await _statuses(project_id, db)


@router.post("/tooling/recheck", response_model=list[ToolStatus])
async def tooling_recheck(project_id: str | None = Query(None),
                          db: AsyncSession = Depends(get_db_session)) -> list[ToolStatus]:
    return await _statuses(project_id, db)
