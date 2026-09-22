"""Safe, local artifact persistence with containment and redaction."""
from __future__ import annotations

import hashlib
import re
from pathlib import Path
from uuid import uuid4

from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.core.paths import get_data_dir, is_path_safe
from app.models import Artifact, ScanSession, ScanTaskRecord

_SECRET = re.compile(r"(?i)(password|secret|token|api[_-]?key)(\s*[=:]\s*)([^\s,;]+)")


def redact_artifact_text(text: str) -> str:
    text = _SECRET.sub(lambda match: f"{match.group(1)}{match.group(2)}[REDACTED]", text)
    text = re.sub(r"\b(?:gsk|sk|ghp)_[A-Za-z0-9_-]{12,}\b", "[REDACTED_SECRET]", text)
    return text


async def persist_text_artifact(scan_id: str, task_key: str, text: str, *, kind: str = "LOG",
                                mime_type: str = "text/plain") -> Artifact:
    """Persist redacted output beneath QSScope-owned storage and record its hash."""
    safe_text = redact_artifact_text(text)
    async with AsyncSessionLocal() as db:
        scan = await db.get(ScanSession, scan_id)
        if scan is None:
            raise ValueError("Unknown scan")
        task = (await db.execute(select(ScanTaskRecord).where(
            ScanTaskRecord.scan_id == scan_id, ScanTaskRecord.task_key == task_key))).scalars().first()
        suffix = ".json" if mime_type == "application/json" else ".log"
        data_root = get_data_dir().resolve()
        directory = data_root / "projects" / scan.project_id / "scans" / scan_id / "raw"
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"{task_key}{suffix}"
        if not is_path_safe(path, data_root):
            raise ValueError("Artifact path escapes QSScope data storage")
        path.write_text(safe_text, encoding="utf-8")
        digest = hashlib.sha256(safe_text.encode()).hexdigest()
        artifact = Artifact(id=str(uuid4()), scan_id=scan_id, task_id=task.id if task else None, kind=kind,
                            relative_path=path.relative_to(data_root).as_posix(), sha256=digest, mime_type=mime_type)
        db.add(artifact)
        await db.commit()
        await db.refresh(artifact)
        return artifact


async def persist_binary_artifact(scan_id: str, task_key: str, data: bytes, *, filename: str,
                                  kind: str, mime_type: str) -> Artifact:
    """Persist bounded binary evidence beneath scan storage."""
    if len(data) > 20_000_000:
        raise ValueError("Binary artifact exceeds the 20 MB safety limit")
    safe_name = re.sub(r"[^A-Za-z0-9._-]", "_", Path(filename).name)[:200]
    if not safe_name:
        raise ValueError("Artifact filename is invalid")
    async with AsyncSessionLocal() as db:
        scan = await db.get(ScanSession, scan_id)
        if scan is None:
            raise ValueError("Unknown scan")
        task = (await db.execute(select(ScanTaskRecord).where(
            ScanTaskRecord.scan_id == scan_id, ScanTaskRecord.task_key == task_key))).scalars().first()
        data_root = get_data_dir().resolve()
        directory = data_root / "projects" / scan.project_id / "scans" / scan_id / "evidence"
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / safe_name
        if not is_path_safe(path, data_root):
            raise ValueError("Artifact path escapes QSScope data storage")
        path.write_bytes(data)
        artifact = Artifact(id=str(uuid4()), scan_id=scan_id, task_id=task.id if task else None,
                            kind=kind, relative_path=path.relative_to(data_root).as_posix(),
                            sha256=hashlib.sha256(data).hexdigest(), mime_type=mime_type)
        db.add(artifact)
        await db.commit()
        await db.refresh(artifact)
        return artifact
