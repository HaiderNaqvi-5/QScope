"""SQLAlchemy models for all entities."""
from sqlalchemy import Column, String, DateTime, JSON, Text
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
    plan = Column(JSON, nullable=False, default=list)
    results = Column(JSON, nullable=False, default=list)
    error = Column(Text, nullable=True)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, server_default=func.now())


class Finding(Base):
    """Quality/security finding."""
    __tablename__ = "findings"
    id = Column(String(36), primary_key=True)
    scan_id = Column(String(36), nullable=False)
    title = Column(String(512), nullable=False)
    severity = Column(String(50))
    created_at = Column(DateTime, server_default=func.now())


class Baseline(Base):
    """Scan baseline for regression."""
    __tablename__ = "baselines"
    id = Column(String(36), primary_key=True)
    project_id = Column(String(36), nullable=False)
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
