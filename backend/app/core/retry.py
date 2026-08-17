"""
Retry with exponential backoff (spec §51).

External services will fail; nothing may retry forever. The fixture adapters of
Phase 2 never fail, so this wrapper is currently a straight pass-through — it
exists because Phases 4–6 wrap every provider call in it.
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
