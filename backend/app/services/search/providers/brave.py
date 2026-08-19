"""
Brave Search provider (spec §28) — the real one.

    GET https://api.search.brave.com/res/v1/web/search
        ?q=…&count=…&country=…&result_filter=web
        X-Subscription-Token: <BRAVE_SEARCH_API_KEY>

    → data["web"]["results"][] → {url, title, description, age, page_age, language}

Four things this class is responsible for, none of which belong further up:

* **the key never leaves the server** (spec §55) — it travels in a header, never in
  a URL or a log line, and no error message quotes it;
* **one query is one billed call**: `count` is capped at Brave's maximum of 20 and
  no paging is attempted, so `SearchUsage.search_api_calls` stays exactly truthful
  (§54);
* **the plan's rate limit is respected** — the free plan allows one request per
  second *per key*, so the limiter is shared across every search in the process and
  a 429 pushes the next call out by whatever `Retry-After` asks for (§52);
* **failures are classified** into "try again" (timeout, 429, 5xx) and "do not
  bother" (401/403 bad key, 422 refused query), which is what stops a wrong key
  from costing three calls per query (§51).

The retry loop itself lives in the pipeline (`core/retry.py`) because it is the
same policy for every provider.
"""

import html
import re
from datetime import datetime
from typing import Any

import httpx

from app.core.errors import ProviderAuthError, ProviderError, ProviderUnavailableError
from app.core.limits import RateLimiter
from app.core.logging import get_logger
from app.models.source import ProviderResult
from app.services.search.providers.base import SearchMarket, SearchProvider

log = get_logger(__name__)

BRAVE_ENDPOINT = "https://api.search.brave.com/res/v1/web/search"

#: Brave's documented maximum for `count`. Asking for more is an error, not a hint.
MAX_COUNT = 20
#: Queries longer than 400 characters are rejected outright.
MAX_QUERY_CHARS = 380
#: However long the provider asks us to wait, waiting minutes would stall a search.
MAX_RETRY_AFTER_S = 10.0

TAGS = re.compile(r"<[^>]+>")
WHITESPACE = re.compile(r"\s+")


class BraveSearchProvider(SearchProvider):
    name = "brave"

    def __init__(
        self,
        api_key: str,
        *,
        endpoint: str = BRAVE_ENDPOINT,
        results_per_query: int = MAX_COUNT,
        timeout_seconds: float = 10.0,
        rate_limit_per_second: float = 1.0,
        safesearch: str = "off",
        client: httpx.AsyncClient | None = None,
        limiter: RateLimiter | None = None,
    ) -> None:
        if not api_key:
            raise ValueError("BraveSearchProvider needs an API key")
        self._key = api_key
        self._endpoint = endpoint
        self._count = min(max(1, results_per_query), MAX_COUNT)
        self._safesearch = safesearch
        self._limiter = limiter or RateLimiter(rate_limit_per_second)
        # A caller-supplied client is what the tests inject; when we build our own
        # we also own closing it (see `aclose`).
        self._owned = client is None
        self._client = client or httpx.AsyncClient(timeout=httpx.Timeout(timeout_seconds))

    async def search(
        self, query: str, limit: int = MAX_COUNT, *, market: SearchMarket | None = None
    ) -> list[ProviderResult]:
        params: dict[str, Any] = {
            "q": _fit(query),
            "count": min(self._count, max(1, limit)),
            # Web results only: news, videos and FAQ blocks are not people.
            "result_filter": "web",
            "safesearch": self._safesearch,
            # `<strong>` markup around matched words would end up in a lead summary.
            "text_decorations": 0,
            # We write the operators ourselves; "correcting" them changes the query.
            "spellcheck": 0,
        }
        if market and market.country:
            params["country"] = market.country
        if market and market.language:
            params["search_lang"] = market.language

        payload = await self._get(params)
        results = [
            result for entry in _web_results(payload) if (result := _to_result(entry, query))
        ]
        log.info(
            "brave_search_completed",
            extra={"results": len(results), "country": params.get("country")},
        )
        return results[:limit]

    async def aclose(self) -> None:
        if self._owned:
            await self._client.aclose()

    # ----------------------------------------------------------------- transport
    async def _get(self, params: dict[str, Any]) -> dict[str, Any]:
        await self._limiter.acquire()
        try:
            response = await self._client.get(
                self._endpoint,
                params=params,
                headers={
                    "Accept": "application/json",
                    "Accept-Encoding": "gzip",
                    # Spec §55: the key is a header, so it stays out of URLs and logs.
                    "X-Subscription-Token": self._key,
                },
            )
        except httpx.TimeoutException as error:
            raise ProviderUnavailableError(
                "Brave Search did not answer in time", provider=self.name
            ) from error
        except httpx.HTTPError as error:
            raise ProviderUnavailableError(
                "Brave Search could not be reached", provider=self.name
            ) from error

        if response.status_code != httpx.codes.OK:
            self._fail(response)

        try:
            payload = response.json()
        except ValueError as error:
            raise ProviderUnavailableError(
                "Brave Search returned a response that is not JSON", provider=self.name
            ) from error
        return payload if isinstance(payload, dict) else {}

    def _fail(self, response: httpx.Response) -> None:
        """Map a status onto an error that knows whether retrying is worth it."""
        status = response.status_code
        log.warning("brave_search_rejected", extra={"status": status, "body": _detail(response)})

        if status in (httpx.codes.UNAUTHORIZED, httpx.codes.FORBIDDEN):
            raise ProviderAuthError(
                f"Brave Search rejected the subscription token ({status}). "
                "Check BRAVE_SEARCH_API_KEY and the plan attached to it.",
                provider=self.name,
                status=status,
            )
        if status == httpx.codes.TOO_MANY_REQUESTS:
            # The provider knows when it will serve us again; the limiter now does too.
            self._limiter.pause(_retry_after(response))
            raise ProviderUnavailableError(
                "Brave Search rate limit reached", provider=self.name, status=status
            )
        if status >= httpx.codes.INTERNAL_SERVER_ERROR:
            raise ProviderUnavailableError(
                f"Brave Search is unavailable ({status})", provider=self.name, status=status
            )
        raise ProviderError(
            f"Brave Search refused the query ({status})", provider=self.name, status=status
        )


# --------------------------------------------------------------------- parsing
def _web_results(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Tolerate a shape we did not expect: no results is a valid answer."""
    web = payload.get("web")
    results = web.get("results") if isinstance(web, dict) else None
    if not isinstance(results, list):
        return []
    return [entry for entry in results if isinstance(entry, dict)]


def _to_result(entry: dict[str, Any], query: str) -> ProviderResult | None:
    url = str(entry.get("url") or "").strip()
    if not url:
        return None
    return ProviderResult(
        url=url,
        title=_text(entry.get("title")),
        snippet=_text(entry.get("description")),
        query=query,
        provider=BraveSearchProvider.name,
        page_age=_moment(entry.get("page_age")),
        age_label=_text(entry.get("age")) or None,
        language=_text(entry.get("language")) or None,
    )


def _text(value: object) -> str:
    """Brave's titles and descriptions can carry markup and entities."""
    if not isinstance(value, str):
        return ""
    return WHITESPACE.sub(" ", html.unescape(TAGS.sub(" ", value))).strip()


def _moment(value: object) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _fit(query: str) -> str:
    """Trim on a word boundary rather than let the provider reject the query."""
    query = WHITESPACE.sub(" ", query).strip()
    if len(query) <= MAX_QUERY_CHARS:
        return query
    cut = query[:MAX_QUERY_CHARS].rsplit(" ", 1)[0]
    log.warning("brave_query_truncated", extra={"from": len(query), "to": len(cut)})
    return cut


def _retry_after(response: httpx.Response) -> float:
    raw = response.headers.get("Retry-After", "")
    try:
        return min(float(raw), MAX_RETRY_AFTER_S)
    except ValueError:
        # A date-formatted Retry-After, or none at all: the plan's own interval
        # is the best guess we have.
        return 1.0


def _detail(response: httpx.Response) -> str:
    """A short, safe echo of the provider's complaint — never our own request."""
    return _text(response.text)[:200]
