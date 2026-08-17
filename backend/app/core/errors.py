"""
Application errors and their HTTP mapping (spec §51).

Services raise domain errors and never import fastapi.HTTPException, so the same
service code can later run inside a worker where HTTP means nothing.
"""

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse


class AppError(Exception):
    status_code = 500
    code = "internal_error"

    def __init__(self, message: str, **context: object) -> None:
        super().__init__(message)
        self.message = message
        self.context = context


class NotFoundError(AppError):
    status_code = 404
    code = "not_found"


class ConflictError(AppError):
    """The entity exists but is in a state that forbids the operation."""

    status_code = 409
    code = "conflict"


class ProviderError(AppError):
    """An external provider failed after exhausting retries (Phase 4+)."""

    status_code = 502
    code = "provider_error"


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def handle_app_error(_: Request, error: AppError) -> JSONResponse:
        return JSONResponse(
            status_code=error.status_code,
            # `detail` is what the frontend's ApiError reads.
            content={"detail": error.message, "code": error.code, **error.context},
        )
