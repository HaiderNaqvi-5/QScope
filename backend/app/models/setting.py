"""Settings model."""
from sqlalchemy import Column, String, Boolean, DateTime
from sqlalchemy.sql import func
from app.core.database import Base


class Setting(Base):
    """Application settings stored in database."""
    __tablename__ = "settings"

    key = Column(String(255), primary_key=True, index=True)
    value = Column(String(4096), nullable=False)
    description = Column(String(1024))
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
