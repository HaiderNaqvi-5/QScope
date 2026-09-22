"""Auditable remediation planning endpoints; filesystem mutation is a later explicit phase."""
from uuid import uuid4
from urllib.parse import urljoin

import httpx

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_session
from pathlib import Path

from app.models import Finding, FindingHistory, Project, RemediationAttempt, RemediationFixPack, ScanSession
from app.schemas.remediation import (RemediationApplyRequest, RemediationAttemptResponse,
                                     FixPackCreate, FixPackResponse,
                                     RemediationDispositionRequest, RemediationQueueItem,
                                     RemediationPatchRequest, RemediationPlanRequest,
                                     ReproductionRequest,
                                     RemediationVerifyRequest, SafeFixQueueRequest,
                                     SafeFixQueueResponse)
from app.schemas.findings import FindingResponse
from app.services.remediation_executor import (apply_patch, create_checkpoint, rollback_checkpoint,
                                               run_verification_check)
from app.services.remediation_policy import remediation_eligibility, validate_unified_patch
from app.services.findings import score_findings
from app.services.release_gate import evaluate_release_gate
from app.services.fix_packs import validate_fix_pack
from app.services.schema_testing import validate_loopback_base_url

router = APIRouter()
FAILED_ATTEMPT_STATES = {"FIX_FAILED", "REGRESSION_INTRODUCED", "ROLLED_BACK", "VERIFICATION_INCONCLUSIVE"}


@router.post("/findings/{finding_id}/remediations/reproduce")
async def reproduce_remediation_finding(finding_id: str, request: ReproductionRequest,
                                        db: AsyncSession = Depends(get_db_session)) -> dict:
    """Replay a safe loopback API scenario and retain only bounded expected-vs-actual evidence."""
    finding = await db.get(Finding, finding_id)
    if not finding:
        raise HTTPException(404, "Finding not found")
    if not request.endpoint.startswith("/") or request.endpoint.startswith("//"):
        raise HTTPException(422, "Reproduction endpoint must be a relative absolute-path URL")
    try:
        base_url = validate_loopback_base_url(request.base_url)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    safe_headers = {key: value for key, value in request.headers.items()
                    if key.lower() not in {"host", "content-length", "connection", "authorization", "cookie"}}
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(10, connect=3), follow_redirects=False) as client:
            response = await client.request(request.method, urljoin(f"{base_url}/", request.endpoint.lstrip("/")),
                                            headers=safe_headers)
        actual_status = response.status_code
        status = "REPRODUCED" if actual_status not in request.expected_status_codes else "NOT_REPRODUCED"
        evidence = {"status": status, "method": request.method, "endpoint": request.endpoint,
                    "expected_status_codes": request.expected_status_codes, "actual_status": actual_status}
    except httpx.HTTPError as exc:
        evidence = {"status": "INCONCLUSIVE", "method": request.method, "endpoint": request.endpoint,
                    "expected_status_codes": request.expected_status_codes, "error": str(exc)[:500]}
    finding.evidence = {**(finding.evidence or {}), "reproduction": evidence}
    await db.commit()
    return evidence


@router.post("/findings/{finding_id}/remediations/plan", response_model=RemediationAttemptResponse, status_code=201)
async def create_remediation_plan(finding_id: str, request: RemediationPlanRequest,
                                  db: AsyncSession = Depends(get_db_session)) -> RemediationAttempt:
    finding = await db.get(Finding, finding_id)
    if not finding:
        raise HTTPException(404, "Finding not found")
    if finding.status == "VERIFIED_FIXED":
        raise HTTPException(409, "Finding is already verified fixed")
    scan = await db.get(ScanSession, finding.scan_id)
    if not scan:
        raise HTTPException(409, "Finding has no scan context")
    if finding_id not in request.plan.finding_ids:
        raise HTTPException(422, "Remediation plan must include the requested finding")
    prior = (await db.execute(select(RemediationAttempt).where(
        RemediationAttempt.finding_id == finding_id).order_by(RemediationAttempt.attempt_number))).scalars().all()
    failed_attempts = sum(item.status in FAILED_ATTEMPT_STATES for item in prior)
    if failed_attempts >= 2:
        raise HTTPException(409, "Automated attempt limit reached; manual review is required")
    reproduction = (finding.evidence or {}).get("reproduction", {})
    reproduced = request.reproduced and reproduction.get("status") == "REPRODUCED"
    eligibility = remediation_eligibility(
        request.plan, request.mode, reproduced=reproduced,
        deterministic_static_evidence=request.deterministic_static_evidence,
    )
    status = "PLAN_VALIDATED" if eligibility.eligible else "MANUAL_REVIEW_REQUIRED"
    attempt = RemediationAttempt(
        id=str(uuid4()), project_id=scan.project_id, scan_id=scan.id, finding_id=finding.id,
        attempt_number=len(prior) + 1, mode=request.mode, status=status, risk=request.plan.risk,
        finding_confidence=str(finding.confidence), fix_confidence=str(request.plan.fix_confidence),
        reproduced=reproduced, deterministic_static_evidence=request.deterministic_static_evidence,
        impact_radius=request.impact_radius, plan=request.plan.model_dump(),
        eligibility=eligibility.model_dump(), verification_plan=request.plan.expected_tests,
        evidence={"reproduction": reproduction} if reproduction else {},
    )
    db.add(attempt)
    await db.commit()
    await db.refresh(attempt)
    return attempt


@router.post("/remediations/{attempt_id}/verify", response_model=RemediationAttemptResponse)
async def verify_remediation(attempt_id: str, request: RemediationVerifyRequest,
                             db: AsyncSession = Depends(get_db_session)) -> RemediationAttempt:
    attempt = await db.get(RemediationAttempt, attempt_id)
    if not attempt:
        raise HTTPException(404, "Remediation attempt not found")
    if attempt.status != "FIX_APPLIED_PENDING_VERIFICATION" or not attempt.checkpoint:
        raise HTTPException(409, "Only an applied remediation can be verified")
    project = await db.get(Project, attempt.project_id)
    finding = await db.get(Finding, attempt.finding_id)
    if not project or not finding:
        raise HTTPException(409, "Remediation verification context is unavailable")
    root = Path(project.root_path)
    evidence = dict(attempt.evidence or {})
    try:
        original = await run_verification_check(root, request.original.model_dump())
        evidence["original_retest"] = original
        if original["status"] != "PASSED":
            outcome = "FIX_FAILED"
        else:
            targeted = [await run_verification_check(root, item.model_dump()) for item in request.targeted]
            evidence["targeted_checks"] = targeted
            if any(item["status"] != "PASSED" for item in targeted):
                outcome = "FIX_FAILED"
            else:
                regression = [await run_verification_check(root, item.model_dump()) for item in request.regression]
                evidence["regression_checks"] = regression
                outcome = "REGRESSION_INTRODUCED" if any(item["status"] != "PASSED" for item in regression) else "VERIFIED_FIXED"
    except (OSError, ValueError) as exc:
        evidence["verification_error"] = str(exc)
        outcome = "VERIFICATION_INCONCLUSIVE"
    if outcome == "VERIFIED_FIXED":
        attempt.status = outcome
        attempt.final_outcome = outcome
        old_finding_status = finding.status
        finding.status = "VERIFIED_FIXED"
        db.add(FindingHistory(id=str(uuid4()), finding_id=finding.id,
                              old_status=old_finding_status, new_status="VERIFIED_FIXED",
                              note=f"Verified by remediation attempt {attempt.id}"))
        scan = await db.get(ScanSession, attempt.scan_id)
        scan_findings = (await db.execute(select(Finding).where(Finding.scan_id == attempt.scan_id))).scalars().all()
        payloads = [FindingResponse.model_validate(item, from_attributes=True).model_dump() for item in scan_findings]
        if scan:
            gate = evaluate_release_gate(payloads, scan.results or [], full_audit=scan.mode == "FULL")
            scan.overall_score = score_findings(payloads, scan.results or [], full_audit=scan.mode == "FULL")
            scan.release_readiness = gate["decision"]
            scan.release_blockers = gate["blockers"]
            scan.is_complete_audit = gate["is_complete_audit"]
    else:
        try:
            evidence["rollback"] = {"status": "ROLLED_BACK", "files": rollback_checkpoint(root, attempt.checkpoint)}
            attempt.status = "ROLLED_BACK"
        except (OSError, RuntimeError, ValueError) as exc:
            evidence["rollback"] = {"status": "MANUAL_REVIEW_REQUIRED", "error": str(exc)}
            attempt.status = "MANUAL_REVIEW_REQUIRED"
        attempt.final_outcome = outcome
    attempt.evidence = evidence
    await db.commit()
    await db.refresh(attempt)
    return attempt


@router.get("/projects/{project_id}/remediations", response_model=list[RemediationAttemptResponse])
async def list_remediations(project_id: str, db: AsyncSession = Depends(get_db_session)) -> list[RemediationAttempt]:
    rows = (await db.execute(select(RemediationAttempt).where(
        RemediationAttempt.project_id == project_id).order_by(RemediationAttempt.created_at, RemediationAttempt.id)
    )).scalars().all()
    return list(rows)


@router.get("/projects/{project_id}/remediation-queue", response_model=list[RemediationQueueItem])
async def remediation_queue(project_id: str,
                            db: AsyncSession = Depends(get_db_session)) -> list[RemediationQueueItem]:
    if not await db.get(Project, project_id):
        raise HTTPException(404, "Project not found")
    rows = (await db.execute(select(RemediationAttempt, Finding).join(
        Finding, Finding.id == RemediationAttempt.finding_id).where(
        RemediationAttempt.project_id == project_id).order_by(
        RemediationAttempt.created_at, RemediationAttempt.id))).all()
    queue = []
    for attempt, finding in rows:
        actions = ["PREVIEW_FIX"]
        if attempt.status == "PATCH_VALIDATED" and attempt.risk in {"SAFE", "MODERATE"} and (
                attempt.eligibility or {}).get("eligible"):
            actions.append("FIX_VERIFY")
        if attempt.status not in {"VERIFIED_FIXED", "ROLLED_BACK", "SKIPPED", "MANUAL_REVIEW_REQUIRED"}:
            actions.extend(["SKIP", "MANUAL_REVIEW"])
        queue.append(RemediationQueueItem(
            attempt=RemediationAttemptResponse.model_validate(attempt, from_attributes=True),
            finding_title=finding.title, severity=finding.severity,
            affected_files=attempt.changed_files or (attempt.plan or {}).get("expected_files", []),
            verification_test_count=1 + len(attempt.verification_plan or []),
            available_actions=actions,
        ))
    return queue


@router.post("/remediations/{attempt_id}/disposition", response_model=RemediationAttemptResponse)
async def set_remediation_disposition(attempt_id: str, request: RemediationDispositionRequest,
                                      db: AsyncSession = Depends(get_db_session)) -> RemediationAttempt:
    attempt = await db.get(RemediationAttempt, attempt_id)
    if not attempt:
        raise HTTPException(404, "Remediation attempt not found")
    if attempt.status in {"FIX_APPLIED_PENDING_VERIFICATION", "VERIFIED_FIXED"}:
        raise HTTPException(409, "An applied or verified remediation cannot be skipped or reclassified")
    attempt.status = request.disposition
    attempt.final_outcome = request.disposition
    attempt.evidence = {**(attempt.evidence or {}), "disposition": {
        "status": request.disposition, "note": request.note}}
    await db.commit()
    await db.refresh(attempt)
    return attempt


@router.post("/projects/{project_id}/remediation-queue/fix-safe", response_model=SafeFixQueueResponse)
async def fix_safe_queue(project_id: str, request: SafeFixQueueRequest,
                         db: AsyncSession = Depends(get_db_session)) -> SafeFixQueueResponse:
    if not await db.get(Project, project_id):
        raise HTTPException(404, "Project not found")
    if len({entry.attempt_id for entry in request.entries}) != len(request.entries):
        raise HTTPException(422, "Each remediation attempt may appear only once in a serialized queue")
    attempts = []
    for entry in request.entries:
        attempt = await db.get(RemediationAttempt, entry.attempt_id)
        if not attempt or attempt.project_id != project_id:
            raise HTTPException(404, f"Remediation attempt {entry.attempt_id} was not found for project")
        if attempt.status != "PATCH_VALIDATED" or attempt.risk not in {"SAFE", "MODERATE"} or not (
                attempt.eligibility or {}).get("eligible"):
            raise HTTPException(409, f"Remediation attempt {entry.attempt_id} is not an eligible validated safe unit")
        applied = await apply_remediation(entry.attempt_id, RemediationApplyRequest(approved=entry.approved), db)
        if applied.status != "FIX_APPLIED_PENDING_VERIFICATION":
            attempts.append(applied)
            continue
        attempts.append(await verify_remediation(entry.attempt_id, entry.verification, db))
    return SafeFixQueueResponse(
        project_id=project_id, processed=len(attempts),
        verified=sum(item.status == "VERIFIED_FIXED" for item in attempts),
        rolled_back=sum(item.status == "ROLLED_BACK" for item in attempts),
        manual_review=sum(item.status == "MANUAL_REVIEW_REQUIRED" for item in attempts),
        attempts=[RemediationAttemptResponse.model_validate(item, from_attributes=True) for item in attempts],
    )


@router.post("/projects/{project_id}/fix-packs", response_model=FixPackResponse, status_code=201)
async def create_fix_pack(project_id: str, request: FixPackCreate,
                          db: AsyncSession = Depends(get_db_session)) -> RemediationFixPack:
    if not await db.get(Project, project_id):
        raise HTTPException(404, "Project not found")
    if len(set(request.finding_ids)) != len(request.finding_ids):
        raise HTTPException(422, "Fix Pack member findings must be unique")
    findings = list((await db.execute(select(Finding).where(Finding.id.in_(request.finding_ids)))).scalars().all())
    if len(findings) != len(request.finding_ids):
        raise HTTPException(404, "One or more Fix Pack findings were not found")
    scans = {item.scan_id for item in findings}
    if len(scans) != 1:
        raise HTTPException(422, "Fix Pack findings must belong to one scan")
    scan = await db.get(ScanSession, next(iter(scans)))
    if not scan or scan.project_id != project_id:
        raise HTTPException(422, "Fix Pack findings do not belong to the selected project")
    scenarios = {finding_id: [item.model_dump() for item in checks]
                 for finding_id, checks in request.verification_scenarios.items()}
    reasons = validate_fix_pack(findings, request.root_cause_id, request.correlation_confidence, scenarios)
    if reasons:
        raise HTTPException(422, " ".join(reasons))
    pack = RemediationFixPack(
        id=str(uuid4()), project_id=project_id, scan_id=scan.id, root_cause_id=request.root_cause_id,
        finding_ids=request.finding_ids, correlation_confidence=str(request.correlation_confidence),
        proposed_shared_correction=request.proposed_shared_correction, risk=request.risk,
        impact_radius=request.impact_radius, verification_scenarios=scenarios,
    )
    db.add(pack)
    await db.commit()
    await db.refresh(pack)
    return pack


@router.get("/projects/{project_id}/fix-packs", response_model=list[FixPackResponse])
async def list_fix_packs(project_id: str,
                         db: AsyncSession = Depends(get_db_session)) -> list[RemediationFixPack]:
    if not await db.get(Project, project_id):
        raise HTTPException(404, "Project not found")
    return list((await db.execute(select(RemediationFixPack).where(
        RemediationFixPack.project_id == project_id).order_by(
        RemediationFixPack.created_at, RemediationFixPack.id))).scalars().all())


@router.get("/remediations/{attempt_id}", response_model=RemediationAttemptResponse)
async def remediation_detail(attempt_id: str, db: AsyncSession = Depends(get_db_session)) -> RemediationAttempt:
    attempt = await db.get(RemediationAttempt, attempt_id)
    if not attempt:
        raise HTTPException(404, "Remediation attempt not found")
    return attempt


@router.post("/remediations/{attempt_id}/patch", response_model=RemediationAttemptResponse)
async def submit_patch(attempt_id: str, request: RemediationPatchRequest,
                       db: AsyncSession = Depends(get_db_session)) -> RemediationAttempt:
    attempt = await db.get(RemediationAttempt, attempt_id)
    if not attempt:
        raise HTTPException(404, "Remediation attempt not found")
    if attempt.status not in {"PLAN_VALIDATED", "PATCH_REJECTED"}:
        raise HTTPException(409, "Patch cannot be replaced in the current remediation state")
    project = await db.get(Project, attempt.project_id)
    if not project:
        raise HTTPException(409, "Remediation project context is unavailable")
    validation = validate_unified_patch(request.patch, Path(project.root_path))
    expected_files = set((attempt.plan or {}).get("expected_files", []))
    unexpected_files = sorted(set(validation.files) - expected_files)
    if unexpected_files:
        validation.accepted = False
        validation.outcome = "PATCH_REJECTED"
        validation.reasons.append("Patch touches files outside the validated remediation plan: " + ", ".join(unexpected_files))
    attempt.patch = request.patch
    attempt.changed_files = validation.files
    attempt.evidence = {**(attempt.evidence or {}), "patch_preflight": validation.model_dump()}
    attempt.status = "PATCH_VALIDATED" if validation.accepted else "PATCH_REJECTED"
    if not validation.accepted:
        attempt.final_outcome = "PATCH_REJECTED"
    await db.commit()
    await db.refresh(attempt)
    return attempt


@router.post("/remediations/{attempt_id}/apply", response_model=RemediationAttemptResponse)
async def apply_remediation(attempt_id: str, request: RemediationApplyRequest,
                            db: AsyncSession = Depends(get_db_session)) -> RemediationAttempt:
    attempt = await db.get(RemediationAttempt, attempt_id)
    if not attempt:
        raise HTTPException(404, "Remediation attempt not found")
    if attempt.status != "PATCH_VALIDATED" or not attempt.patch:
        raise HTTPException(409, "A validated patch is required before application")
    action = (attempt.eligibility or {}).get("action")
    if attempt.mode == "SUGGEST_ONLY":
        raise HTTPException(409, "Suggest Only mode never modifies project files")
    if action != "AUTO_APPLY" and not request.approved:
        raise HTTPException(409, "Assisted remediation requires explicit approval")
    project = await db.get(Project, attempt.project_id)
    if not project:
        raise HTTPException(409, "Remediation project context is unavailable")
    root = Path(project.root_path)
    checkpoint = create_checkpoint(root, attempt.id, attempt.changed_files, attempt.verification_plan or [])
    attempt.checkpoint = checkpoint
    attempt.status = "CHECKPOINT_CREATED"
    await db.commit()
    try:
        changed = apply_patch(root, attempt.patch, checkpoint)
    except ValueError as exc:
        attempt.status = "PATCH_REJECTED"
        attempt.final_outcome = "PATCH_REJECTED"
        attempt.evidence = {**(attempt.evidence or {}), "application_error": str(exc)}
    except (OSError, RuntimeError) as exc:
        attempt.status = "MANUAL_REVIEW_REQUIRED"
        attempt.final_outcome = "MANUAL_REVIEW_REQUIRED"
        attempt.evidence = {**(attempt.evidence or {}), "application_error": str(exc)}
    else:
        attempt.changed_files = changed
        attempt.status = "FIX_APPLIED_PENDING_VERIFICATION"
        attempt.evidence = {**(attempt.evidence or {}), "patch_applied": True}
    await db.commit()
    await db.refresh(attempt)
    return attempt
