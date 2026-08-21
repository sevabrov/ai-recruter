"""
What one search is allowed to spend (spec §52, §54).

Phase 5 could read a page. This is the part that decides *how many*, and it exists
because of a measured run: 11 candidate URLs, 28 requests to the service, 2 usable
pages, and a balance that ran out before the other 99 candidates were reached. Three
mistakes were behind that number, and there is a test here for each.

* **a paid read was retried.** MAX_RETRIES is for calls that cost nothing to repeat;
  the service bills a request it served, and a timeout on our side does not un-bill
  it. So a page is attempted once and then falls back to its snippet.
* **nothing capped the total.** A live search finds a hundred candidates, and
  reading all of them is a plan's monthly credits. `PageBudget` is the ceiling, and
  it sits next to the thing that spends the money.
* **the counters flattered us.** Only successful reads were counted, so the usage
  screen reported two pages while the provider's dashboard reported a spent
  balance. Every served request is counted now, and credits are in plan units.

The rule the file is built around: **a limit may cost depth, never coverage.** A
page the budget refuses still becomes a lead from its search snippet.
"""

import httpx
import pytest

from app.core.errors import ProviderError, ProviderUnavailableError
from app.models.scrape import ScrapeOutcome
from app.services.scraping.base import ExtractionCost
from app.services.scraping.budget import PageBudget
from app.services.scraping.cache import CachedPageReader
from app.services.scraping.fallback import FallbackProfileExtractor
from app.services.scraping.snippet_extractor import SnippetProfileExtractor
from tests.test_scrape_cache import workspace
from tests.test_scrapegraph_extractor import INSTAGRAM, completed, reader

pytestmark = pytest.mark.anyio


def elsewhere(handle: str):
    """The same shape of Instagram URL, a different person."""
    return INSTAGRAM.model_copy(
        update={
            "url": f"https://www.instagram.com/{handle}/",
            "canonical_url": f"https://instagram.com/{handle}",
            "title": f"Marta Ruiz (@{handle}) • Instagram photos and videos",
        }
    )


def counting(payload: dict | None = None, status: int = 200):
    """A transport that answers the same way every time and counts the requests."""
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        return httpx.Response(status, json=payload if payload is not None else completed())

    return calls, handler


# ------------------------------------------------------------------- the ceiling


async def test_the_budget_stops_paying_after_the_pages_it_allows():
    calls, handler = counting()
    page_reader = reader(handler, budget=PageBudget(2))

    outcomes = [await page_reader.read(elsewhere(f"person{index}")) for index in range(5)]

    assert len(calls) == 2, "the third page must not reach the service"
    assert [read.outcome for read in outcomes] == [
        ScrapeOutcome.OK,
        ScrapeOutcome.OK,
        ScrapeOutcome.SKIPPED,
        ScrapeOutcome.SKIPPED,
        ScrapeOutcome.SKIPPED,
    ]
    assert (page_reader.cost.pages_read, page_reader.cost.pages_skipped) == (2, 3)
    assert page_reader.cost.credits == 2 * 10


async def test_a_budget_of_zero_means_unlimited():
    """The demo and the tests want no ceiling; a ceiling of zero would read nothing."""
    calls, handler = counting()
    page_reader = reader(handler, budget=PageBudget(0))

    for index in range(4):
        await page_reader.read(elsewhere(f"person{index}"))

    assert len(calls) == 4
    assert page_reader.cost.pages_skipped == 0


async def test_a_refused_request_gives_its_slot_back():
    """
    A 429 cost nothing, so it must not cost a page either. Otherwise one bad minute
    from the provider silently shrinks the search.
    """
    budget = PageBudget(2)
    page_reader = reader(
        counting({"error": {"type": "rate_limited", "message": "slow down"}}, 429)[1],
        budget=budget,
    )

    with pytest.raises(ProviderUnavailableError):
        await page_reader.read(INSTAGRAM)

    assert (budget.spent, budget.remaining) == (0, 2)
    assert page_reader.cost.credits == 0


async def test_an_empty_balance_does_not_consume_the_budget_either():
    budget = PageBudget(3)
    page_reader = reader(
        counting({"error": {"type": "insufficient_credits", "message": "empty"}}, 402)[1],
        budget=budget,
    )

    with pytest.raises(ProviderError):
        await page_reader.read(INSTAGRAM)

    assert budget.spent == 0


async def test_the_skipped_page_says_why_in_words_the_operator_can_read():
    page_reader = reader(counting()[1], budget=PageBudget(1))

    await page_reader.read(INSTAGRAM)
    refused = await page_reader.read(elsewhere("marta.ruiz"))

    assert refused.outcome is ScrapeOutcome.SKIPPED
    assert refused.detail and "1 paid pages" in refused.detail
    assert refused.profile is None


# ---------------------------------------------------------------- what it costs


async def test_a_page_that_answered_too_late_was_still_paid_for():
    """
    The credit is spent when the service serves the request, and our timeout does not
    give it back. Counting only the answers we could use is what reported a search
    as costing two pages while 400 credits were gone.
    """

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("too slow", request=request)

    page_reader = reader(handler)

    with pytest.raises(ProviderUnavailableError):
        await page_reader.read(INSTAGRAM)

    assert page_reader.cost.pages_read == 0, "nothing was read"
    assert (page_reader.cost.paid_attempts, page_reader.cost.credits) == (1, 10)


async def test_a_connection_that_never_opened_is_not_billed():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("no route", request=request)

    page_reader = reader(handler, budget=PageBudget(2))

    with pytest.raises(ProviderUnavailableError):
        await page_reader.read(INSTAGRAM)

    assert (page_reader.cost.paid_attempts, page_reader.cost.credits) == (0, 0)
    assert page_reader.budget.spent == 0


async def test_credits_follow_the_plan_not_the_page_count():
    """The v2 response reports no credits, so what a page costs is configuration."""
    page_reader = reader(counting()[1], credits_per_page=25)

    await page_reader.read(INSTAGRAM)

    assert page_reader.cost.credits == 25


async def test_one_page_is_attempted_once_and_then_falls_back(settings):
    """
    The chain the container builds: a page that times out is not read again — it is
    read *differently*, from the search result, and the lead survives.
    """

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("too slow", request=request)

    cost = ExtractionCost()
    page_reader = reader(handler, cost=cost)
    chain = FallbackProfileExtractor(page_reader, SnippetProfileExtractor(), attempts=1, cost=cost)

    profile = await chain.extract(INSTAGRAM)

    assert profile is not None, "the timeout must not lose the candidate"
    assert profile.extractor == "snippet"
    assert cost.paid_attempts == 1, "one attempt, one credit — not three"


# ------------------------------------------------------- and what is remembered


async def test_a_page_the_budget_refused_is_not_recorded_against_its_platform(settings):
    """
    `GET /sources` answers "can this platform be read". A page we chose not to open
    says nothing about the platform, so it is not stored — otherwise running out of
    budget would make Instagram look unreadable.
    """
    cost = ExtractionCost()
    page_reader = reader(counting()[1], budget=PageBudget(1), cost=cost)

    async with workspace(settings) as repository:
        cache = CachedPageReader(page_reader, repository, ttl_hours=168, cost=cost)

        await cache.read(INSTAGRAM)
        skipped = await cache.read(elsewhere("marta.ruiz"))

        stored = await repository.get_scrape(INSTAGRAM.canonical_url)
        missing = await repository.get_scrape("https://instagram.com/marta.ruiz")
        report = await repository.source_reliability()

    assert skipped.outcome is ScrapeOutcome.SKIPPED
    assert stored is not None and stored.outcome is ScrapeOutcome.OK
    assert missing is None, "a page that was never opened has no verdict to store"
    assert sum(record.pages for record in report) == 1


async def test_a_cached_page_is_free_and_the_budget_never_sees_it(settings):
    """
    The budget sits *behind* the cache: re-reading last week's page costs nothing, so
    a search whose candidates are all cached spends no budget at all (spec §53).
    """
    cost = ExtractionCost()
    budget = PageBudget(1)
    page_reader = reader(counting()[1], budget=budget, cost=cost)

    async with workspace(settings) as repository:
        cache = CachedPageReader(page_reader, repository, ttl_hours=168, cost=cost)

        first = await cache.read(INSTAGRAM)
        again = await cache.read(INSTAGRAM)

    assert first.outcome is ScrapeOutcome.OK
    assert again.outcome is ScrapeOutcome.OK, "the cache answered, not the budget"
    assert (budget.spent, cost.pages_cached, cost.pages_skipped) == (1, 1, 0)
