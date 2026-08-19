"""
Application errors and their HTTP mapping (spec §51).

Services raise domain errors and never import fastapi.HTTPException, so the same
service code can later run inside a worker where HTTP means nothing.
"""

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy.exc import DisconnectionError, InterfaceError, OperationalError, SQLAlchemyError

from app.core.logging import get_logger

log = get_logger(__name__)

#: Failures that mean "the store is not reachable", as opposed to "this statement
#: was wrong" — the difference between a 503 the client can retry and a 500.
CONNECTION_FAILURES = (OSError, InterfaceError, OperationalError, DisconnectionError)


class AppError(Exception):
    status_code = 500
    code = "internal_error"
    #: Whether doing the exact same thing again could succeed. `core/retry.py`
    #: reads this, so "the key is wrong" costs one call instead of three.
    retryable = False

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
    """
    An external provider failed. The default is *not* retryable: a query the
    provider refused will be refused again. The subclasses below say otherwise.
    """

    status_code = 502
    code = "provider_error"


class ProviderUnavailableError(ProviderError):
    """A timeout, a rate limit or a 5xx — the same call may well work in a moment."""

    code = "provider_unavailable"
    retryable = True


class ProviderAuthError(ProviderError):
    """The provider rejected our credentials. Retrying spends calls for nothing."""

    code = "provider_auth_failed"


class StorageError(AppError):
    """The database refused or dropped the connection."""

    status_code = 503
    code = "database_unavailable"


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def handle_app_error(_: Request, error: AppError) -> JSONResponse:
        return JSONResponse(
            status_code=error.status_code,
            # `detail` is what the frontend's ApiError reads.
            content={"detail": error.message, "code": error.code, **error.context},
        )

    # OSError is here because that is what a refused TCP connection actually raises
    # on the way to Postgres — asyncpg does not wrap it. Provider failures never
    # reach this handler: they are raised as ProviderError (Phase 4+).
    @app.exception_handler(SQLAlchemyError)
    @app.exception_handler(OSError)
    async def handle_storage_error(_: Request, error: Exception) -> JSONResponse:
        """
        A database that is down is not a bug in the request. Answering 503 with a
        code the client can recognise beats a bare 500, and the driver's message —
        which can contain the connection string — never reaches the browser.
        """
        unavailable = isinstance(error, CONNECTION_FAILURES)
        log.error(
            "storage_error",
            extra={"error": type(error).__name__, "unavailable": unavailable},
            exc_info=True,
        )
        if unavailable:
            return JSONResponse(
                status_code=StorageError.status_code,
                content={"detail": "The database is not available", "code": StorageError.code},
            )
        # A statement the database refused is our bug, not an outage.
        return JSONResponse(
            status_code=500,
            content={"detail": "The request could not be stored", "code": "storage_error"},
        )
