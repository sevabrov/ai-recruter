"""
Retry with exponential backoff (spec §51).

External services will fail, and nothing may retry forever. Two rules:

* the number of attempts is bounded by configuration (`MAX_RETRIES`);
* an error that says "this will fail again" is not retried at all — a rejected
  API key or a malformed query costs one call, not three. Errors advertise that
  themselves through `AppError.retryable`, so this module needs no list of
  provider-specific status codes.
"""

import asyncio
from collections.abc import Awaitable, Callable
from typing import TypeVar

from app.core.logging import get_logger

T = TypeVar("T")
log = get_logger(__name__)


async def retry_async(
    operation: Callable[[], Awaitable[T]],
    *,
    attempts: int = 3,
    base_delay: float = 0.25,
    retry_on: tuple[type[Exception], ...] = (Exception,),
    label: str = "operation",
) -> T:
    last: Exception | None = None
    for attempt in range(1, max(1, attempts) + 1):
        try:
            return await operation()
        except retry_on as error:
            last = error
            # Unknown failures (a timeout, a dropped socket) are worth another go;
            # a domain error only is when it says so.
            if not getattr(error, "retryable", True):
                log.warning(
                    "retry_pointless",
                    extra={"label": label, "error": type(error).__name__},
                )
                raise
            if attempt >= attempts:
                break
            delay = base_delay * 2 ** (attempt - 1)
            log.warning(
                "retry_scheduled",
                extra={"label": label, "attempt": attempt, "delay_s": round(delay, 3)},
            )
            await asyncio.sleep(delay)

    log.error("retry_exhausted", extra={"label": label, "attempts": attempts})
    assert last is not None
    raise last
