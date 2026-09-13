"""Common API models and responses."""
from pydantic import BaseModel, Field
from typing import Any, Optional


class ErrorResponse(BaseModel):
    """Standard error response."""
    error: str = Field(..., description="Error message")
    detail: Optional[str] = Field(None, description="Detailed error information")
    status_code: int = Field(..., description="HTTP status code")


class SuccessResponse(BaseModel):
    """Standard success response wrapper."""
    success: bool = True
    data: Any = Field(..., description="Response data")
    message: Optional[str] = Field(None, description="Optional message")


class HealthResponse(BaseModel):
    """Health check response."""
    status: str = Field(..., description="Health status")
    message: str = Field(..., description="Status message")
    version: str = Field(default="0.1.0", description="API version")
