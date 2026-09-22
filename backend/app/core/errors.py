"""Canonical, non-leaking API error envelopes."""
from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)


def error_envelope(code: str, message: str, *, details: Any = None, recoverable: bool = True,
                   suggested_action: str | None = None) -> dict[str, Any]:
    return {"error": {"code": code, "message": message, "details": details or {},
                      "recoverable": recoverable, "suggested_action": suggested_action}}


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(HTTPException)
    async def http_error(_request: Request, exc: HTTPException) -> JSONResponse:
        detail = exc.detail
        if isinstance(detail, dict) and {"code", "message"} <= detail.keys():
            payload = error_envelope(detail["code"], detail["message"], details=detail.get("details"),
                                     recoverable=detail.get("recoverable", exc.status_code < 500),
                                     suggested_action=detail.get("suggested_action"))
        else:
            message = str(detail) if detail else "Request failed"
            code = {404: "NOT_FOUND", 409: "CONFLICT", 422: "INVALID_REQUEST",
                    503: "SERVICE_UNAVAILABLE"}.get(exc.status_code, "REQUEST_FAILED")
            payload = error_envelope(code, message, recoverable=exc.status_code < 500)
        return JSONResponse(status_code=exc.status_code, content=payload, headers=exc.headers)

    @app.exception_handler(RequestValidationError)
    async def validation_error(_request: Request, exc: RequestValidationError) -> JSONResponse:
        details = [{"location": list(error["loc"]), "message": error["msg"], "type": error["type"]}
                   for error in exc.errors()]
        return JSONResponse(status_code=422, content=error_envelope(
            "VALIDATION_ERROR", "The request did not match the required contract.", details=details,
            suggested_action="Correct the highlighted fields and retry.",
        ))

    @app.exception_handler(Exception)
    async def unexpected_error(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("Unhandled API error for %s", request.url.path, exc_info=exc)
        return JSONResponse(status_code=500, content=error_envelope(
            "INTERNAL_ERROR", "QSScope could not complete the request.", recoverable=False,
            suggested_action="Review local QSScope logs and retry after resolving the reported problem.",
        ))
