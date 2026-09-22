"""Runtime profile request and response contracts."""
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator


class RuntimeProfileCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    working_directory: str = "."
    command: list[str] = Field(min_length=1, max_length=32)
    local_url: str
    health_endpoint: str | None = None
    environment_file: str | None = None
    startup_timeout_seconds: int = Field(default=30, ge=1, le=300)
    trusted_default: bool = False

    @field_validator("command")
    @classmethod
    def command_parts_are_bounded(cls, value: list[str]) -> list[str]:
        if any(not part or len(part) > 2048 or "\x00" in part for part in value):
            raise ValueError("command arguments must be non-empty and bounded")
        return value


class RuntimeStartRequest(BaseModel):
    approved: bool = False


class RuntimeProfileResponse(BaseModel):
    id: str
    project_id: str
    name: str
    working_directory: str
    command: list[str]
    local_url: str
    health_endpoint: str | None
    environment_file: str | None
    startup_timeout_seconds: int
    trusted_default: bool
    status: Literal["STOPPED", "STARTING", "READY", "FAILED", "STOPPING"]
    pid: int | None
    last_error: str | None
    created_at: datetime | None

    model_config = {"from_attributes": True}


class RuntimeLogResponse(BaseModel):
    profile_id: str
    output: str
    truncated: bool
