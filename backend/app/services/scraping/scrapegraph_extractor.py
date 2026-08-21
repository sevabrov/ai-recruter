"""
ScrapeGraphAI page reader (spec §33–34) — the real one, against the **v2 API**.

    POST https://v2-api.scrapegraphai.com/api/extract
        SGAI-APIKEY: <SCRAPEGRAPH_API_KEY>
        {"url": …, "prompt": …, "schema": {…}}

    → {"id": …, "json": {…}, "raw": null,
       "usage": {"promptTokens": …, "completionTokens": …},
       "metadata": {"fetch": {…}, "chunker": {…}}}

    errors → {"error": {"type": "insufficient_credits", "message": …}}

The Extract service answers synchronously: one request, one result, no job to poll.
(The legacy `api.scrapegraphai.com/v1/smartscraper` endpoint and its dashboard are
deprecated; `SCRAPEGRAPH_ENDPOINT` is configuration, so an account on either one
needs no code change.)

What this class is responsible for, and nothing above it is:

* **the key stays server-side** (spec §55) — a header, never a query parameter, and
  no error message quotes it;
* **structured output only** (§34) — the request carries `PageExtraction`'s JSON
  schema, so the model cannot answer in prose, and a response that does not fit the
  schema is treated as an unreadable page rather than parsed loosely;
* **a bad page is not a failure** — a login wall, a consent screen or a shop is an
  *outcome*, classified and returned, because Milestone 5 asks us to record which
  sources can be read at all. Only the service failing raises;
* **credits are money** (§54) — every request the service *served* is billed, our
  timeouts included, and the count goes into `ExtractionCost` next to the tokens
  the service reports. The v2 response carries no credit figure, so what a page
  costs in plan units is configuration (`SCRAPEGRAPH_CREDITS_PER_PAGE`);
* **a search may not spend without a ceiling** (§52) — `PageBudget` is consulted
  before the request, and a refused page is answered `SKIPPED` rather than
  fetched, so the chain above falls back to the snippet;
* **the plan's rate limit is per key** (§52), so the limiter is shared by every
  search in the process.
"""

from typing import Any

import httpx
from pydantic import ValidationError

from app.core.errors import ProviderAuthError, ProviderError, ProviderUnavailableError
from app.core.limits import RateLimiter
from app.core.logging import get_logger
from app.models.profile import ExtractedProfile
from app.models.scrape import ScrapeOutcome
from app.models.source import DiscoveredUrl
from app.services.scraping.base import ExtractionCost, PageRead, PageReader
from app.services.scraping.budget import PageBudget
from app.services.scraping.page_schema import (
    EXTRACTION_PROMPT,
    PageExtraction,
    content_hash,
    is_a_person,
    output_schema,
    to_profile,
)

log = get_logger(__name__)

SCRAPEGRAPH_ENDPOINT = "https://v2-api.scrapegraphai.com/api/extract"

#: Error types the API names for "the key itself is the problem" (401/403).
AUTH_ERRORS = ("auth_missing_key", "auth_invalid_key")
#: …and for an empty balance (402). Retrying either cannot help.
CREDIT_ERRORS = ("insufficient_credits",)

#: Words in a fetch diagnostic or an error that mean "the page would not let us in"
#: rather than "we broke". Stored verbatim either way, so a wrong guess is visible.
ACCESS_DENIED = (
    "block",
    "forbidden",
    "403",
    "401",
    "login",
    "sign in",
    "signin",
    "captcha",
    "denied",
    "robots",
    "not authorized",
    "unauthorized",
    "consent",
    "paywall",
    "unavailable for legal",
)

#: However long the provider asks us to wait, waiting minutes would stall a search.
MAX_RETRY_AFTER_S = 10.0


class ScrapeGraphProfileExtractor(PageReader):
    name = "scrapegraph"

    def __init__(
        self,
        api_key: str,
        *,
        endpoint: str = SCRAPEGRAPH_ENDPOINT,
        timeout_seconds: float = 120.0,
        rate_limit_per_second: float = 1.0,
        credits_per_page: int = 10,
        cost: ExtractionCost | None = None,
        budget: PageBudget | None = None,
        client: httpx.AsyncClient | None = None,
        limiter: RateLimiter | None = None,
    ) -> None:
        if not api_key:
            raise ValueError("ScrapeGraphProfileExtractor needs an API key")
        self._key = api_key
        self._endpoint = endpoint
        self._credits_per_page = max(1, credits_per_page)
        self.cost = cost or ExtractionCost()
        # No budget object means no ceiling, which is what a script or a unit test
        # wants. The pipeline always passes one.
        self.budget = budget or PageBudget()
        self._limiter = limiter or RateLimiter(rate_limit_per_second)
        # A caller-supplied client is what the tests inject; when we build our own
        # we also own closing it.
        self._owned = client is None
        self._client = client or httpx.AsyncClient(timeout=httpx.Timeout(timeout_seconds))

    async def extract(self, url: DiscoveredUrl) -> ExtractedProfile | None:
        return (await self.read(url)).profile

    async def read(self, url: DiscoveredUrl) -> PageRead:
        if not self.budget.take():
            # Deliberately not an error and deliberately not a verdict about the
            # page: the caller falls back to the snippet, and the cache does not
            # store this (`services/scraping/cache.py`).
            self.cost.pages_skipped += 1
            return PageRead(
                outcome=ScrapeOutcome.SKIPPED,
                detail=f"This search had already read its {self.budget.limit} paid pages",
            )

        charged = self.cost.paid_attempts
        try:
            payload = await self._request(url.canonical_url)
        except Exception:
            # A request the service refused (a 429, an empty balance) cost nothing,
            # so it must not cost a page from the budget either.
            if self.cost.paid_attempts == charged:
                self.budget.refund()
            raise
        return self._interpret(payload, url)

    async def aclose(self) -> None:
        if self._owned:
            await self._client.aclose()

    # ----------------------------------------------------------------- transport
    async def _request(self, page_url: str) -> dict[str, Any]:
        await self._limiter.acquire()
        try:
            response = await self._client.post(
                self._endpoint,
                json={
                    "url": page_url,
                    "prompt": EXTRACTION_PROMPT,
                    # Structured extraction, not a conversation (spec §34).
                    "schema": output_schema(),
                },
                headers={
                    "Accept": "application/json",
                    # Spec §55: the key is a header, so it stays out of URLs and logs.
                    "SGAI-APIKEY": self._key,
                },
            )
        except httpx.TimeoutException as error:
            # The request reached the service and the page was being rendered, so
            # the credit is gone whether or not the answer arrived in time. Charging
            # it here is what stops the usage screen from reporting a cheap search
            # while the provider's dashboard reports a spent balance.
            self._charge()
            raise ProviderUnavailableError(
                "ScrapeGraphAI did not answer in time", provider=self.name
            ) from error
        except httpx.HTTPError as error:
            raise ProviderUnavailableError(
                "ScrapeGraphAI could not be reached", provider=self.name
            ) from error

        if response.status_code >= httpx.codes.BAD_REQUEST:
            self._fail(response)

        try:
            payload = response.json()
        except ValueError as error:
            raise ProviderUnavailableError(
                "ScrapeGraphAI returned a response that is not JSON", provider=self.name
            ) from error

        # The request was served, so it is billed whatever the page turned out to be.
        self._charge()
        self.cost.pages_read += 1
        self._count_tokens(payload if isinstance(payload, dict) else {})
        return payload if isinstance(payload, dict) else {}

    def _charge(self) -> None:
        """One served request: an attempt on the bill and the plan's credits with it."""
        self.cost.paid_attempts += 1
        self.cost.credits += self._credits_per_page

    def _count_tokens(self, payload: dict[str, Any]) -> None:
        """The service reports what the extraction actually consumed (spec §54)."""
        usage = payload.get("usage")
        if not isinstance(usage, dict):
            return
        self.cost.tokens_in += _int(usage.get("promptTokens"))
        self.cost.tokens_out += _int(usage.get("completionTokens"))

    def _fail(self, response: httpx.Response) -> None:
        """Map a failure onto an error that knows whether retrying is worth it (§51)."""
        status = response.status_code
        kind, message = _error(response)
        log.warning(
            "scrapegraph_rejected", extra={"status": status, "type": kind, "detail": message}
        )

        if kind in AUTH_ERRORS or status in (httpx.codes.UNAUTHORIZED, httpx.codes.FORBIDDEN):
            raise ProviderAuthError(
                f"ScrapeGraphAI rejected the API key ({status}). "
                "Check SCRAPEGRAPH_API_KEY — keys from the deprecated dashboard are not "
                "accepted by the v2 API.",
                provider=self.name,
                status=status,
            )
        if kind in CREDIT_ERRORS or status == httpx.codes.PAYMENT_REQUIRED:
            raise ProviderError(
                "ScrapeGraphAI reports no credits left for this key. "
                "Top up or upgrade the plan attached to SCRAPEGRAPH_API_KEY.",
                provider=self.name,
                status=status,
            )
        if status == httpx.codes.TOO_MANY_REQUESTS:
            # The provider knows when it will serve us again; the limiter now does too.
            self._limiter.pause(_retry_after(response))
            raise ProviderUnavailableError(
                "ScrapeGraphAI rate limit reached", provider=self.name, status=status
            )
        if status >= httpx.codes.INTERNAL_SERVER_ERROR:
            raise ProviderUnavailableError(
                f"ScrapeGraphAI is unavailable ({status})", provider=self.name, status=status
            )
        raise ProviderError(
            f"ScrapeGraphAI refused the request ({status}): {message or kind}".strip(": "),
            provider=self.name,
            status=status,
        )

    # ---------------------------------------------------------------- the answer
    def _interpret(self, payload: dict[str, Any], url: DiscoveredUrl) -> PageRead:
        """
        Classify what came back. Nothing here raises: a page that cannot be used is
        an outcome, and recording *which* kind is the point (Milestone 5).
        """
        extracted = payload.get("json")
        blocked = _fetch_refused(payload)

        if not isinstance(extracted, dict) or not any(
            _present(value) for value in extracted.values()
        ):
            # A page behind a login wall answers with an empty extraction and a fetch
            # diagnostic that says why, so the two cases are told apart here.
            outcome = ScrapeOutcome.BLOCKED if blocked else ScrapeOutcome.EMPTY
            log.info(
                "scrapegraph_unusable",
                extra={"url": url.canonical_url, "outcome": outcome.value},
            )
            return PageRead(outcome=outcome, detail=blocked or "The page yielded no fields")

        try:
            page = PageExtraction.model_validate(extracted)
        except ValidationError as invalid:
            # The model answered outside its schema. Reading it loosely is how
            # invented data gets in, so this counts as an unreadable page.
            log.warning(
                "scrapegraph_schema_violation",
                extra={"url": url.canonical_url, "errors": invalid.error_count()},
            )
            return PageRead(
                outcome=ScrapeOutcome.EMPTY,
                detail="The extraction did not fit the schema",
                content_hash=content_hash(extracted),
            )

        digest = content_hash(extracted)
        if not is_a_person(page):
            return PageRead(
                outcome=ScrapeOutcome.NOT_A_PERSON,
                content_hash=digest,
                detail=_short(page.name or url.title),
            )

        return PageRead(
            outcome=ScrapeOutcome.OK,
            profile=to_profile(page, url, self.name),
            content_hash=digest,
        )


# --------------------------------------------------------------------- helpers
def _fetch_refused(payload: dict[str, Any]) -> str | None:
    """
    Whether the fetch diagnostics say the page refused us, and in what words.

    The shape of `metadata.fetch` is the provider's, not ours, so this reads it
    defensively: any status at or above 400, or any wording that means "denied",
    counts — and whatever it said is stored, so a wrong guess is inspectable.
    """
    metadata = payload.get("metadata")
    fetch = metadata.get("fetch") if isinstance(metadata, dict) else None
    if not isinstance(fetch, dict) or not fetch:
        return None

    status = _int(fetch.get("status") or fetch.get("statusCode"))
    if status >= httpx.codes.BAD_REQUEST:
        return _short(f"The page answered {status}")

    spoken = " ".join(str(value) for value in fetch.values() if isinstance(value, str | int | bool))
    return _short(spoken) if _mentions(spoken, ACCESS_DENIED) else None


def _error(response: httpx.Response) -> tuple[str, str]:
    """
    `(type, message)` from the documented error envelope, or a short safe echo of
    whatever arrived instead. Never our own request, never a key.
    """
    try:
        body = response.json()
    except ValueError:
        return "", _short(response.text) or ""

    error = body.get("error") if isinstance(body, dict) else None
    if isinstance(error, dict):
        return str(error.get("type") or ""), _short(str(error.get("message") or "")) or ""
    if isinstance(error, str):
        return "", _short(error) or ""
    return "", _short(response.text) or ""


def _present(value: object) -> bool:
    """Whether a field carries anything. `false`, `0`, `[]` and `{}` do not."""
    if isinstance(value, dict):
        return any(_present(inner) for inner in value.values())
    if isinstance(value, list):
        return any(_present(inner) for inner in value)
    if isinstance(value, bool):
        return value
    if isinstance(value, int | float):
        return value != 0
    return bool(value)


def _mentions(text: str, needles: tuple[str, ...]) -> bool:
    lowered = (text or "").lower()
    return any(needle in lowered for needle in needles)


def _int(value: object) -> int:
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0


def _short(text: str, limit: int = 200) -> str | None:
    cleaned = " ".join((text or "").split())[:limit]
    return cleaned or None


def _retry_after(response: httpx.Response) -> float:
    raw = response.headers.get("Retry-After", "")
    try:
        return min(float(raw), MAX_RETRY_AFTER_S)
    except ValueError:
        return 1.0
