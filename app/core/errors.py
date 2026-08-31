"""Application error types and FastAPI exception handlers.

Errors are values, not panics: every failure path raises AppError (or
subclasses) with an HTTP status, a stable machine `code`, and an optional
request_id propagated back in the ErrorResponse.
"""

from __future__ import annotations

from typing import Any

import structlog
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.schemas import ErrorResponse

logger = structlog.get_logger(__name__)


class AppError(Exception):
    def __init__(
        self,
        status_code: int = 500,
        code: str = "internal_error",
        message: str = "Internal error",
        detail: str | None = None,
        request_id: str | None = None,
    ) -> None:
        self.status_code = status_code
        self.code = code
        self.message = message
        self.detail = detail
        self.request_id = request_id
        super().__init__(message)


class AuthError(AppError):
    def __init__(
        self,
        message: str = "Unauthorized",
        detail: str | None = None,
        request_id: str | None = None,
    ) -> None:
        super().__init__(401, "unauthorized", message, detail, request_id)


class NotFoundError(AppError):
    def __init__(
        self,
        message: str = "Not found",
        detail: str | None = None,
        request_id: str | None = None,
    ) -> None:
        super().__init__(404, "not_found", message, detail, request_id)


class BudgetError(AppError):
    def __init__(
        self,
        message: str = "Budget exceeded",
        detail: str | None = None,
        request_id: str | None = None,
    ) -> None:
        super().__init__(402, "budget_exceeded", message, detail, request_id)


class UpstreamError(AppError):
    def __init__(
        self,
        status_code: int = 502,
        message: str = "Upstream provider error",
        detail: str | None = None,
        request_id: str | None = None,
    ) -> None:
        super().__init__(status_code, "upstream_error", message, detail, request_id)


def _request_id(request: Request) -> str | None:
    return getattr(request.state, "request_id", None)


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _app_error_handler(request: Request, exc: AppError) -> JSONResponse:
        rid = exc.request_id or _request_id(request)
        logger.warning(
            "error.handled",
            code=exc.code,
            status=exc.status_code,
            detail=exc.detail,
        )
        return JSONResponse(
            status_code=exc.status_code,
            content=ErrorResponse(
                error=exc.code,
                detail=exc.detail or exc.message,
                request_id=rid,
                status_code=exc.status_code,
            ).model_dump(),
            headers={"X-Request-ID": rid} if rid else None,
        )

    @app.exception_handler(RequestValidationError)
    async def _validation_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
        rid = _request_id(request)
        logger.warning("error.validation", errors=exc.errors()[:5])
        return JSONResponse(
            status_code=422,
            content=ErrorResponse(
                error="validation_error",
                detail=str(exc.errors()[:5]),
                request_id=rid,
                status_code=422,
            ).model_dump(),
            headers={"X-Request-ID": rid} if rid else None,
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        rid = _request_id(request)
        detail: Any = exc.detail
        return JSONResponse(
            status_code=exc.status_code,
            content=ErrorResponse(
                error="http_error",
                detail=str(detail),
                request_id=rid,
                status_code=exc.status_code,
            ).model_dump(),
            headers={"X-Request-ID": rid} if rid else None,
        )

    @app.exception_handler(Exception)
    async def _unhandled_handler(request: Request, exc: Exception) -> JSONResponse:
        rid = _request_id(request)
        logger.exception("error.unhandled", exc=str(exc))
        return JSONResponse(
            status_code=500,
            content=ErrorResponse(
                error="internal_error",
                detail="Internal server error",
                request_id=rid,
                status_code=500,
            ).model_dump(),
            headers={"X-Request-ID": rid} if rid else None,
        )


__all__ = [
    "AppError",
    "AuthError",
    "NotFoundError",
    "BudgetError",
    "UpstreamError",
    "register_error_handlers",
]
