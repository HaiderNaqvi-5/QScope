"""SQLAlchemy models for all entities."""
from sqlalchemy import Boolean, Column, DateTime, Integer, JSON, String, Text
from sqlalchemy.sql import func
from app.core.database import Base


class Project(Base):
    """QSScope project."""
    __tablename__ = "projects"
    id = Column(String(36), primary_key=True)
    name = Column(String(255), nullable=False)
    root_path = Column(String(2048), unique=True, nullable=False)
    project_model = Column(JSON, nullable=False, default=dict)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class ScanSession(Base):
    """Scan session."""
    __tablename__ = "scan_sessions"
    id = Column(String(36), primary_key=True)
    project_id = Column(String(36), nullable=False)
    status = Column(String(50), default="pending")
    mode = Column(String(20), default="STANDARD")
    approved = Column(String(10), default="false")
    plan = Column(JSON, nullable=False, default=list)
    results = Column(JSON, nullable=False, default=list)
    error = Column(Text, nullable=True)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    git_commit = Column(String(64), nullable=True)
    git_branch = Column(String(512), nullable=True)
    project_fingerprint = Column(String(64), nullable=True)
    overall_score = Column(Integer, nullable=True)
    is_complete_audit = Column(Boolean, nullable=True)
    release_readiness = Column(String(50), nullable=True)
    release_blockers = Column(JSON, nullable=False, default=list)
    created_at = Column(DateTime, server_default=func.now())


class ScanTaskRecord(Base):
    """Durable state for one planned tool execution."""
    __tablename__ = "scan_tasks"
    id = Column(String(36), primary_key=True)
    scan_id = Column(String(36), nullable=False, index=True)
    task_key = Column(String(255), nullable=False)
    stage = Column(String(100), nullable=False)
    tool = Column(String(100), nullable=False)
    adapter = Column(String(100), nullable=False)
    target = Column(String(2048), nullable=False, default=".")
    status = Column(String(50), nullable=False, default="PENDING")
    depends_on = Column(JSON, nullable=False, default=list)
    requires_confirmation = Column(Boolean, nullable=False, default=False)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    exit_code = Column(Integer, nullable=True)
    duration_ms = Column(Integer, nullable=True)
    summary = Column(Text, nullable=True)


class ScanEventRecord(Base):
    """Persisted SSE envelope for refresh/reconnect recovery."""
    __tablename__ = "scan_events"
    id = Column(String(36), primary_key=True)
    scan_id = Column(String(36), nullable=False, index=True)
    event = Column(String(100), nullable=False)
    task_id = Column(String(255), nullable=True)
    payload = Column(JSON, nullable=False, default=dict)
    created_at = Column(DateTime, server_default=func.now(), index=True)


class Artifact(Base):
    """Traceable local output produced by a scan task."""
    __tablename__ = "artifacts"
    id = Column(String(36), primary_key=True)
    scan_id = Column(String(36), nullable=False, index=True)
    task_id = Column(String(36), nullable=True)
    kind = Column(String(30), nullable=False)
    relative_path = Column(String(2048), nullable=False)
    sha256 = Column(String(64), nullable=False)
    mime_type = Column(String(255), nullable=False)
    created_at = Column(DateTime, server_default=func.now())


class TestRun(Base):
    __tablename__ = "test_runs"
    id = Column(String(36), primary_key=True)
    scan_id = Column(String(36), nullable=False, index=True)
    task_id = Column(String(36), nullable=True)
    suite_name = Column(String(512), nullable=False)
    framework = Column(String(100), nullable=False)
    discovered = Column(Integer, nullable=False, default=0)
    passed = Column(Integer, nullable=False, default=0)
    failed = Column(Integer, nullable=False, default=0)
    skipped = Column(Integer, nullable=False, default=0)
    duration_ms = Column(Integer, nullable=True)
    coverage_percent = Column(String(20), nullable=True)
    status = Column(String(50), nullable=False)
    raw_artifact_id = Column(String(36), nullable=True)
    details = Column(JSON, nullable=False, default=dict)
    created_at = Column(DateTime, server_default=func.now())


class RuntimeProfile(Base):
    """Persisted, user-reviewable local service launch configuration."""
    __tablename__ = "runtime_profiles"
    id = Column(String(36), primary_key=True)
    project_id = Column(String(36), nullable=False, index=True)
    name = Column(String(255), nullable=False)
    working_directory = Column(String(2048), nullable=False, default=".")
    command = Column(JSON, nullable=False, default=list)
    local_url = Column(String(2048), nullable=False)
    health_endpoint = Column(String(2048), nullable=True)
    environment_file = Column(String(2048), nullable=True)
    startup_timeout_seconds = Column(Integer, nullable=False, default=30)
    trusted_default = Column(Boolean, nullable=False, default=False)
    status = Column(String(50), nullable=False, default="STOPPED")
    pid = Column(Integer, nullable=True)
    last_error = Column(Text, nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class ManualTestCase(Base):
    __tablename__ = "manual_test_cases"
    id = Column(String(36), primary_key=True)
    project_id = Column(String(36), nullable=False, index=True)
    module = Column(String(255), nullable=False)
    feature = Column(String(255), nullable=True)
    preconditions = Column(JSON, nullable=False, default=list)
    steps = Column(JSON, nullable=False, default=list)
    expected_result = Column(Text, nullable=False)
    actual_result = Column(Text, nullable=True)
    status = Column(String(30), nullable=False, default="NOT_RUN")
    severity = Column(String(30), nullable=True)
    notes = Column(Text, nullable=True)
    source = Column(String(40), nullable=False, default="MANUAL")
    accepted = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class ManualTestEvidence(Base):
    __tablename__ = "manual_test_evidence"
    id = Column(String(36), primary_key=True)
    test_id = Column(String(36), nullable=False, index=True)
    relative_path = Column(String(2048), nullable=False)
    sha256 = Column(String(64), nullable=False)
    mime_type = Column(String(255), nullable=False)
    original_name = Column(String(512), nullable=False)
    created_at = Column(DateTime, server_default=func.now())


class GeneratedTestCase(Base):
    """Deterministically derived contract, logical, or boundary scenario."""
    __tablename__ = "generated_test_cases"
    id = Column(String(36), primary_key=True)
    project_id = Column(String(36), nullable=False, index=True)
    scan_id = Column(String(36), nullable=True, index=True)
    category = Column(String(30), nullable=False, index=True)
    title = Column(String(512), nullable=False)
    method = Column(String(16), nullable=False)
    endpoint = Column(String(2048), nullable=False)
    actor = Column(String(255), nullable=True)
    input_data = Column(JSON, nullable=False, default=dict)
    expected = Column(JSON, nullable=False, default=dict)
    status = Column(String(30), nullable=False, default="GENERATED")
    evidence = Column(JSON, nullable=False, default=dict)
    source_path = Column(String(2048), nullable=False)
    fingerprint = Column(String(64), nullable=False, unique=True, index=True)
    created_at = Column(DateTime, server_default=func.now())


class BehaviorCoverageRecord(Base):
    __tablename__ = "behavior_coverage"
    id = Column(String(36), primary_key=True)
    project_id = Column(String(36), nullable=False, index=True)
    scan_id = Column(String(36), nullable=True, index=True)
    capability_key = Column(String(512), nullable=False)
    category = Column(String(50), nullable=False, index=True)
    title = Column(String(512), nullable=False)
    criticality = Column(String(30), nullable=False, default="NORMAL")
    coverage_status = Column(String(30), nullable=False)
    source = Column(String(50), nullable=False)
    evidence = Column(JSON, nullable=False, default=dict)
    fingerprint = Column(String(64), nullable=False, unique=True, index=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class Finding(Base):
    """Quality/security finding."""
    __tablename__ = "findings"
    id = Column(String(36), primary_key=True)
    scan_id = Column(String(36), nullable=False)
    title = Column(String(512), nullable=False)
    severity = Column(String(50))
    tool = Column(String(100), nullable=False, default="qsscope")
    stage = Column(String(100), nullable=False, default="UNKNOWN")
    file_path = Column(String(2048), nullable=True)
    line = Column(String(30), nullable=True)
    message = Column(Text, nullable=False, default="")
    category = Column(String(100), nullable=False, default="CODE_QUALITY")
    subcategory = Column(String(100), nullable=True)
    description = Column(Text, nullable=False, default="")
    confidence = Column(String(20), nullable=False, default="0.75")
    rule_id = Column(String(512), nullable=True)
    start_line = Column(Integer, nullable=True)
    end_line = Column(Integer, nullable=True)
    endpoint = Column(String(2048), nullable=True)
    evidence = Column(JSON, nullable=False, default=dict)
    raw_artifact_id = Column(String(36), nullable=True)
    why_it_matters = Column(Text, nullable=False, default="")
    recommendation = Column(Text, nullable=False, default="")
    suggested_patch = Column(Text, nullable=True)
    suggested_test = Column(Text, nullable=True)
    sources = Column(JSON, nullable=False, default=list)
    correlation_key = Column(String(128), nullable=True, index=True)
    fingerprint = Column(String(128), nullable=False, default="")
    status = Column(String(30), nullable=False, default="OPEN")
    created_at = Column(DateTime, server_default=func.now())


class FindingSource(Base):
    __tablename__ = "finding_sources"
    id = Column(String(36), primary_key=True)
    finding_id = Column(String(36), nullable=False, index=True)
    tool = Column(String(100), nullable=False)
    rule_id = Column(String(512), nullable=True)
    evidence = Column(JSON, nullable=False, default=dict)
    raw_artifact_id = Column(String(36), nullable=True)
    created_at = Column(DateTime, server_default=func.now())


class FindingHistory(Base):
    __tablename__ = "finding_history"
    id = Column(String(36), primary_key=True)
    finding_id = Column(String(36), nullable=False, index=True)
    old_status = Column(String(30), nullable=True)
    new_status = Column(String(30), nullable=False)
    note = Column(Text, nullable=True)
    created_at = Column(DateTime, server_default=func.now())


class RemediationAttempt(Base):
    """Auditable state for one independently planned remediation unit."""
    __tablename__ = "remediation_attempts"
    id = Column(String(36), primary_key=True)
    project_id = Column(String(36), nullable=False, index=True)
    scan_id = Column(String(36), nullable=False, index=True)
    finding_id = Column(String(36), nullable=False, index=True)
    attempt_number = Column(Integer, nullable=False, default=1)
    mode = Column(String(30), nullable=False, default="ASSISTED")
    status = Column(String(50), nullable=False, default="PLAN_VALIDATED")
    risk = Column(String(30), nullable=False)
    finding_confidence = Column(String(20), nullable=False)
    fix_confidence = Column(String(20), nullable=False)
    reproduced = Column(Boolean, nullable=False, default=False)
    deterministic_static_evidence = Column(Boolean, nullable=False, default=False)
    impact_radius = Column(JSON, nullable=False, default=dict)
    plan = Column(JSON, nullable=False, default=dict)
    eligibility = Column(JSON, nullable=False, default=dict)
    patch = Column(Text, nullable=True)
    changed_files = Column(JSON, nullable=False, default=list)
    checkpoint = Column(JSON, nullable=False, default=dict)
    verification_plan = Column(JSON, nullable=False, default=list)
    evidence = Column(JSON, nullable=False, default=dict)
    final_outcome = Column(String(50), nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class RemediationFixPack(Base):
    """Durable shared-root-cause proposal for strongly correlated findings."""
    __tablename__ = "remediation_fix_packs"
    id = Column(String(36), primary_key=True)
    project_id = Column(String(36), nullable=False, index=True)
    scan_id = Column(String(36), nullable=False, index=True)
    root_cause_id = Column(String(128), nullable=False, index=True)
    finding_ids = Column(JSON, nullable=False, default=list)
    correlation_confidence = Column(String(20), nullable=False)
    proposed_shared_correction = Column(Text, nullable=False)
    risk = Column(String(30), nullable=False)
    impact_radius = Column(JSON, nullable=False, default=dict)
    verification_scenarios = Column(JSON, nullable=False, default=dict)
    status = Column(String(50), nullable=False, default="PROPOSED")
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class Baseline(Base):
    """Scan baseline for regression."""
    __tablename__ = "baselines"
    id = Column(String(36), primary_key=True)
    project_id = Column(String(36), nullable=False)
    fingerprints = Column(JSON, nullable=False, default=list)
    created_at = Column(DateTime, server_default=func.now())


class Report(Base):
    """Generated report."""
    __tablename__ = "reports"
    id = Column(String(36), primary_key=True)
    scan_id = Column(String(36), nullable=False)
    format = Column(String(20))
    created_at = Column(DateTime, server_default=func.now())


class Setting(Base):
    """Application settings."""
    __tablename__ = "settings"
    key = Column(String(255), primary_key=True, index=True)
    value = Column(String(4096), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
