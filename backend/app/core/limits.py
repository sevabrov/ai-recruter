"""
Per-provider rate limiting (spec §52).

Concurrency limits alone are not enough for a paid search API: Brave's entry plan
allows one request per second no matter how many searches are running, so the
throttle has to live next to the *key*, not next to the search. One limiter
instance is therefore shared by every job in the process — which is exactly why
the provider is built once in the container and not once per pipeline.

`pause()` exists for the case the provider knows better than we do: a 429 with a
`Retry-After` header moves the next allowed call, so the retry that follows waits
for as long as the provider asked instead of a guessed backoff.
"""

import asyncio
import time


class RateLimiter:
    """Spaces calls at most one per `1 / per_second`. `per_second <= 0` means off."""

    def __init__(self, per_second: float) -> None:
        self._interval = 1 / per_second if per_second > 0 else 0.0
        self._lock = asyncio.Lock()
        self._next_at = 0.0

    async def acquire(self) -> None:
        while True:
            async with self._lock:
                now = time.monotonic()
                if now >= self._next_at:
                    self._next_at = now + self._interval
                    return
                wait = self._next_at - now
            # Released the lock first: waiting inside it would serialise every
            # caller behind the longest sleep.
            await asyncio.sleep(wait)

    def pause(self, seconds: float) -> None:
        """Hold every caller back for `seconds`, e.g. after a rate-limit response."""
        self._next_at = max(self._next_at, time.monotonic() + max(0.0, seconds))
