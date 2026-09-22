from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db_session
from app.models import Finding, Project
from app.schemas.llm import AIActionRequest, AIActionResponse, DisclosureResponse, ModelsResponse
from app.services.llm.context import build_context
from app.services.llm.providers.groq import GroqProvider
from app.services.llm.schemas import LLMRequest

router = APIRouter()
POLICY_VERSION = "groq-v1"
DISCLOSURE = ("AI assistance uses the Groq API. Relevant redacted source snippets and finding "
              "context may be sent to Groq for analysis. Deterministic scans remain local.")


def _provider() -> GroqProvider:
    return GroqProvider(api_key=settings.GROQ_API_KEY, base_url=settings.GROQ_BASE_URL,
                        timeout=settings.GROQ_TIMEOUT_SECONDS, max_retries=settings.GROQ_MAX_RETRIES,
                        max_tokens=settings.GROQ_MAX_TOKENS)


def _disclosure(project: Project) -> DisclosureResponse:
    value = (project.project_model or {}).get("ai_disclosure", {})
    timestamp = value.get("acknowledged_at") if value.get("policy_version") == POLICY_VERSION else None
    return DisclosureResponse(project_id=project.id, acknowledged=bool(timestamp), policy_version=POLICY_VERSION,
                              acknowledged_at=timestamp, disclosure=DISCLOSURE)


@router.get("/projects/{project_id}/ai-disclosure", response_model=DisclosureResponse)
async def disclosure(project_id: str, db: AsyncSession = Depends(get_db_session)) -> DisclosureResponse:
    project = await db.get(Project, project_id)
    if not project:
        raise HTTPException(404, "Project not found")
    return _disclosure(project)


@router.post("/projects/{project_id}/ai-disclosure/acknowledge", response_model=DisclosureResponse)
async def acknowledge(project_id: str, db: AsyncSession = Depends(get_db_session)) -> DisclosureResponse:
    project = await db.get(Project, project_id)
    if not project:
        raise HTTPException(404, "Project not found")
    model = dict(project.project_model or {})
    model["ai_disclosure"] = {"policy_version": POLICY_VERSION, "acknowledged_at": datetime.now(timezone.utc).isoformat()}
    project.project_model = model
    await db.commit()
    await db.refresh(project)
    return _disclosure(project)


@router.get("/settings/ai/models", response_model=ModelsResponse)
async def models() -> ModelsResponse:
    if not settings.QSSCOPE_LLM_ENABLED or not settings.GROQ_API_KEY:
        raise HTTPException(503, "AI_UNAVAILABLE: Groq is disabled or GROQ_API_KEY is missing")
    provider = _provider()
    try:
        return ModelsResponse(models=await provider.list_models())
    except Exception as exc:
        raise HTTPException(503, f"AI_UNAVAILABLE: {exc.__class__.__name__}") from exc
    finally:
        await provider.close()


@router.post("/findings/{finding_id}/ai", response_model=AIActionResponse)
async def finding_action(finding_id: str, request: AIActionRequest,
                         db: AsyncSession = Depends(get_db_session)) -> AIActionResponse:
    finding = await db.get(Finding, finding_id)
    if not finding:
        raise HTTPException(404, "Finding not found")
    from app.models import ScanSession
    scan = await db.get(ScanSession, finding.scan_id)
    project = await db.get(Project, scan.project_id) if scan else None
    if not project:
        raise HTTPException(404, "Project not found")
    if not _disclosure(project).acknowledged:
        raise HTTPException(409, "AI_DISCLOSURE_REQUIRED")
    if not settings.QSSCOPE_LLM_ENABLED or not settings.GROQ_API_KEY:
        return AIActionResponse(status="AI_UNAVAILABLE", reason="Groq is disabled or GROQ_API_KEY is missing")
    try:
        line = int(finding.line) if finding.line else None
    except ValueError:
        line = None
    context, manifest = build_context(Path(project.root_path), finding.file_path, line)
    correlation_id = str(uuid4())
    llm_request = LLMRequest(job=request.job, finding={
        "title": finding.title, "severity": finding.severity, "tool": finding.tool,
        "stage": finding.stage, "message": finding.message, "file_path": finding.file_path, "line": finding.line,
    }, context=context, manifest=manifest, model=settings.GROQ_MODEL, correlation_id=correlation_id)
    provider = _provider()
    try:
        response = await provider.generate_structured(llm_request)
    except Exception as exc:
        return AIActionResponse(status="AI_UNAVAILABLE", reason=exc.__class__.__name__, correlation_id=correlation_id,
                                manifest=manifest)
    finally:
        await provider.close()
    return AIActionResponse(status="READY", result=response.result, model=response.model,
                            correlation_id=response.correlation_id, manifest=response.manifest)
