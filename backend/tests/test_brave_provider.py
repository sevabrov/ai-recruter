"""
The Brave Search provider (spec §28, §51–52).

No test here reaches the network: the provider takes its HTTP client, so the
transport is a canned Brave response. That is the point — the behaviour worth
testing is what we do with an answer, not that Brave answers.
"""

import time

import httpx
import pytest

from app.core.errors import ProviderAuthError, ProviderError, ProviderUnavailableError
from app.core.limits import RateLimiter
from app.core.retry import retry_async
from app.models.search import SearchCriteria
from app.services.search.providers.base import SearchMarket
from app.services.search.providers.brave import BraveSearchProvider

#: One web result in the shape Brave documents, markup and all.
PAYLOAD = {
    "type": "search",
    "web": {
        "results": [
            {
                "title": "Anna L&oacute;pez (@anna.beauty) &bull; <strong>Instagram</strong>",
                "url": "https://www.instagram.com/anna.beauty/",
                "description": "12.5K Followers &mdash; <strong>network marketing</strong>",
                "age": "3 days ago",
                "page_age": "2026-08-15T10:00:00",
                "language": "es",
            },
            {
                "title": "MIHI Cosmetics",
                "url": "https://mihi.example.com/shop",
                "description": "Buy online",
            },
            {"title": "No URL, no result", "description": "…"},
        ]
    },
}


def provider(handler, **kwargs) -> BraveSearchProvider:
    """A provider whose transport is a function, and whose throttle is off."""
    return BraveSearchProvider(
        "secret-token",
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
        rate_limit_per_second=0,
        **kwargs,
    )


def answers(payload: dict, status: int = 200):
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(status, json=payload)

    return handler


def recorder(payload: dict, status: int = 200) -> tuple[list[httpx.Request], object]:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(status, json=payload)

    return seen, handler


# ------------------------------------------------------------------- the answer


async def test_a_brave_result_becomes_a_provider_result():
    results = await provider(answers(PAYLOAD)).search("site:instagram.com MIHI Spain")

    first = results[0]
    assert first.url == "https://www.instagram.com/anna.beauty/"
    # Markup and entities are stripped: this text ends up in a lead summary.
    assert first.title == "Anna López (@anna.beauty) • Instagram"
    assert first.snippet == "12.5K Followers — network marketing"
    assert first.provider == "brave"
    assert first.query == "site:instagram.com MIHI Spain"
    assert first.language == "es"
    assert first.age_label == "3 days ago"
    assert first.page_age is not None and first.page_age.year == 2026


async def test_a_result_without_a_url_is_dropped_not_stored():
    results = await provider(answers(PAYLOAD)).search("q")

    assert len(results) == 2  # the shop stays: classifying it is the next stage's job
    assert all(result.url for result in results)


@pytest.mark.parametrize(
    "payload",
    [{}, {"web": None}, {"web": {"results": "nope"}}, {"web": {"results": [None, 7]}}],
)
async def test_a_payload_we_did_not_expect_is_no_results_not_a_crash(payload):
    assert await provider(answers(payload)).search("q") == []


# ------------------------------------------------------------------ the request


async def test_the_key_travels_in_a_header_and_never_in_the_url():
    """Spec §55: a key in a query string ends up in logs, proxies and referrers."""
    seen, handler = recorder(PAYLOAD)

    await provider(handler).search("q")

    assert seen[0].headers["X-Subscription-Token"] == "secret-token"
    assert "secret-token" not in str(seen[0].url)


async def test_the_query_is_aimed_at_the_country_the_user_asked_for():
    seen, handler = recorder(PAYLOAD)
    criteria = SearchCriteria(location={"country": "Spain"}, languages=["Spanish", "English"])

    await provider(handler).search("MIHI", market=SearchMarket.from_criteria(criteria))

    params = seen[0].url.params
    assert params["country"] == "ES"
    assert params["result_filter"] == "web"
    # Three languages means "any of them" — pinning the index to one would hide two.
    assert "search_lang" not in params


async def test_one_language_is_worth_sending():
    seen, handler = recorder(PAYLOAD)
    criteria = SearchCriteria(location={"country": "Poland"}, languages=["Polish"])

    await provider(handler).search("MIHI", market=SearchMarket.from_criteria(criteria))

    assert seen[0].url.params["search_lang"] == "pl"


async def test_a_country_brave_has_no_market_for_searches_worldwide():
    """Better a global search than a query rejected for an unsupported parameter."""
    market = SearchMarket.from_criteria(SearchCriteria(location={"country": "Czechia"}))

    assert market.country is None


async def test_count_never_exceeds_the_providers_maximum():
    seen, handler = recorder(PAYLOAD)

    await provider(handler, results_per_query=100).search("q", limit=100)

    assert seen[0].url.params["count"] == "20"


async def test_a_very_long_query_is_trimmed_instead_of_being_rejected():
    seen, handler = recorder(PAYLOAD)
    query = " ".join(["network marketing beauty leader"] * 40)

    await provider(handler).search(query)

    sent = seen[0].url.params["q"]
    assert len(sent) < 400
    assert not sent.endswith(" ")  # cut on a word boundary


# ----------------------------------------------------------------- the failures


@pytest.mark.parametrize("status", [401, 403])
async def test_a_rejected_key_fails_once_and_says_what_to_fix(status):
    """Retrying a bad token spends the quota three times over for nothing (§51)."""
    seen, handler = recorder({"error": "unauthorized"}, status=status)
    brave = provider(handler)

    with pytest.raises(ProviderAuthError) as failure:
        await retry_async(lambda: brave.search("q"), attempts=3, base_delay=0)

    assert len(seen) == 1
    assert "BRAVE_SEARCH_API_KEY" in str(failure.value)
    assert "secret-token" not in str(failure.value)


async def test_a_rate_limit_is_retried_and_waits_as_long_as_asked():
    calls: list[float] = []

    def handler(_: httpx.Request) -> httpx.Response:
        calls.append(time.monotonic())
        if len(calls) == 1:
            return httpx.Response(429, headers={"Retry-After": "0.2"}, json={})
        return httpx.Response(200, json=PAYLOAD)

    brave = provider(handler)
    results = await retry_async(lambda: brave.search("q"), attempts=3, base_delay=0)

    assert len(results) == 2
    # The second attempt waited for the limiter the 429 pushed forward, not for the
    # backoff — `base_delay=0` means the retry loop itself would not have waited.
    assert calls[1] - calls[0] >= 0.2


async def test_a_provider_outage_is_retried_but_bounded():
    seen, handler = recorder({"error": "boom"}, status=503)
    brave = provider(handler)

    with pytest.raises(ProviderUnavailableError):
        await retry_async(lambda: brave.search("q"), attempts=3, base_delay=0)

    assert len(seen) == 3  # never forever


async def test_a_query_the_provider_refuses_is_not_retried():
    seen, handler = recorder({"error": "invalid"}, status=422)
    brave = provider(handler)

    with pytest.raises(ProviderError) as failure:
        await retry_async(lambda: brave.search("q"), attempts=3, base_delay=0)

    assert len(seen) == 1
    assert failure.value.status_code == 502  # our clients see a provider error


async def test_a_timeout_is_worth_another_attempt():
    attempts = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        attempts["count"] += 1
        if attempts["count"] == 1:
            raise httpx.ReadTimeout("too slow", request=request)
        return httpx.Response(200, json=PAYLOAD)

    brave = provider(handler)

    assert len(await retry_async(lambda: brave.search("q"), attempts=3, base_delay=0)) == 2


async def test_a_response_that_is_not_json_does_not_become_a_lead():
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="<html>gateway</html>")

    with pytest.raises(ProviderUnavailableError):
        await provider(handler).search("q")


# ---------------------------------------------------------------- the throttle


async def test_the_limiter_spaces_calls_because_the_plan_counts_per_key():
    """Spec §52: ten concurrent searches still share one request per second."""
    limiter = RateLimiter(per_second=20)

    started = time.monotonic()
    for _ in range(3):
        await limiter.acquire()
    elapsed = time.monotonic() - started

    assert elapsed >= 0.1  # two gaps of 50 ms


async def test_a_limiter_that_is_switched_off_does_not_wait():
    limiter = RateLimiter(per_second=0)

    started = time.monotonic()
    for _ in range(50):
        await limiter.acquire()

    assert time.monotonic() - started < 0.1


def test_a_provider_without_a_key_is_a_programming_error():
    """`build_search_provider` checks the key; this is the backstop."""
    with pytest.raises(ValueError):
        BraveSearchProvider("")
