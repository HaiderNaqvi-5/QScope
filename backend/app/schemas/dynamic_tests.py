from typing import Literal

from pydantic import BaseModel, Field, field_validator


class ConcurrencyRunRequest(BaseModel):
    base_url: str = Field(min_length=1, max_length=2048)
    method: Literal["GET", "HEAD", "POST", "PUT", "PATCH"] = "GET"
    endpoint: str = Field(min_length=1, max_length=2048)
    request_count: int = Field(default=3, ge=2, le=10)
    json_body: dict | list | None = None
    actor_headers: dict[str, str] = Field(default_factory=dict)
    expected_statuses: list[int] = Field(default_factory=lambda: [200], min_length=1, max_length=20)
    max_successes: int | None = Field(default=None, ge=0, le=10)
    disposable_confirmed: bool = False
    scan_id: str | None = None

    @field_validator("endpoint")
    @classmethod
    def local_path(cls, value: str) -> str:
        if not value.startswith("/") or "://" in value:
            raise ValueError("endpoint must be a relative absolute-path beginning with /")
        return value


class ResilienceCaseRequest(BaseModel):
    kind: Literal["INVALID_JSON", "EMPTY_BODY", "INVALID_CONTENT_TYPE"]
    expected_statuses: list[int] = Field(default_factory=lambda: [400, 415, 422], min_length=1, max_length=20)


class ResilienceRunRequest(BaseModel):
    base_url: str = Field(min_length=1, max_length=2048)
    method: Literal["POST", "PUT", "PATCH"] = "POST"
    endpoint: str = Field(min_length=1, max_length=2048)
    cases: list[ResilienceCaseRequest] = Field(min_length=1, max_length=10)
    actor_headers: dict[str, str] = Field(default_factory=dict)
    disposable_confirmed: bool = False
    scan_id: str | None = None

    @field_validator("endpoint")
    @classmethod
    def local_path(cls, value: str) -> str:
        if not value.startswith("/") or "://" in value:
            raise ValueError("endpoint must be a relative absolute-path beginning with /")
        return value
