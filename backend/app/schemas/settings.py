"""Settings schemas for API."""
from pydantic import BaseModel, Field
from typing import Optional


class SettingsUpdate(BaseModel):
    """Settings update request."""
    debug: Optional[bool] = None
    log_level: Optional[str] = None
    enable_llm_features: Optional[bool] = None
    enable_advanced_testing: Optional[bool] = None


class SettingsResponse(BaseModel):
    """Settings response."""
    debug: bool
    log_level: str
    enable_llm_features: bool
    enable_advanced_testing: bool
    backend_host: str
    backend_port: int
    data_dir: str


class AIStatusResponse(BaseModel):
    provider: str
    status: str
    model: str
    max_tokens: int
    timeout_seconds: int
    source_upload_default: bool
    note: str
