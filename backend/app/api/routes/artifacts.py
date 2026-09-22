"""Contained access to locally persisted scan evidence."""
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_session
from app.core.paths import get_data_dir, is_path_safe
from app.models import Artifact

router = APIRouter()


@router.get("/scans/{scan_id}/artifacts")
async def list_artifacts(scan_id: str, db: AsyncSession = Depends(get_db_session)) -> list[dict]:
    rows = (await db.execute(select(Artifact).where(Artifact.scan_id == scan_id)
                             .order_by(Artifact.created_at, Artifact.id))).scalars().all()
    return [{"id": row.id, "scan_id": row.scan_id, "task_id": row.task_id, "kind": row.kind,
             "relative_path": row.relative_path, "sha256": row.sha256, "mime_type": row.mime_type,
             "created_at": row.created_at} for row in rows]


@router.get("/artifacts/{artifact_id}/download")
async def download_artifact(artifact_id: str, db: AsyncSession = Depends(get_db_session)) -> FileResponse:
    artifact = await db.get(Artifact, artifact_id)
    if artifact is None:
        raise HTTPException(404, "Artifact not found")
    data_root = get_data_dir().resolve()
    path = data_root / Path(artifact.relative_path)
    if not is_path_safe(path, data_root) or not path.is_file():
        raise HTTPException(404, "Artifact file is unavailable")
    return FileResponse(path, media_type=artifact.mime_type, filename=path.name)
