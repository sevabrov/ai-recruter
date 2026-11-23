"""
Adapter wiring — the one place that answers "what is plugged in right now?".

Selection is by configuration (spec §46–47): a provider is used when its key is
set, otherwise a stand-in takes its place and `/health` says which is which, so
nobody mistakes stand-in output for live results.

The stand-ins are not interchangeable, and the choice of extractor depends on the
search above it:

* fixture search + fixture extraction — offline. They search a catalogue handed
  in at startup; the app hands in none, so an offline search finds no one. Only
  the test suite gives them people to find.
* **live search + snippet extraction** — Phase 4. Real URLs, and profiles built
  from the result metadata the search API returned, because a live search that
  reported nothing would be worse than nothing. Never invented from a catalogue.
* **live search + ScrapeGraphAI** — Phase 5. The candidate pages are opened and
  read, through a cache so no page is paid for twice, with the snippet extractor
  behind it for the pages that will not open at all.
"""

from dataclasses import dataclass

import httpx

from app.core.config import Settings
from app.core.limits import RateLimiter
from app.core.logging import get_logger
from app.db.repository import Repository
from app.models.lead import Lead
from app.services.brief.parser import OpenAIBriefParser, ResilientBriefParser
from app.services.extraction.signal_detector import (
    BudgetedSignalDetector,
    FixtureSignalDetector,
    LlmSignalDetector,
    SignalDetector,
)
from app.services.scraping.base import ExtractionCost, PageReader, ProfileExtractor
from app.services.scraping.browser_reader import (
    BrowserPageReader,
    BrowserPool,
    RoutingPageReader,
)
from app.services.scraping.budget import PageBudget
from app.services.scraping.cache import CachedPageReader
from app.services.scraping.fallback import FallbackProfileExtractor
from app.services.scraping.fixture_extractor import FixtureProfileExtractor
from app.services.scraping.scrapegraph_extractor import ScrapeGraphProfileExtractor
from app.services.scraping.snippet_extractor import SnippetProfileExtractor
from app.services.search.providers.base import SearchProvider
from app.services.search.providers.brave import BraveSearchProvider
from app.services.search.providers.fixture import FixtureSearchProvider

log = get_logger(__name__)


def use_live_search(settings: Settings) -> bool:
    """
    `SEARCH_PROVIDER=fixture` forces the offline stand-in even with a key
    configured, which is what the test suite uses. Anything else means "live if
    we can": a key is required, never assumed.
    """
    return settings.search_provider != "fixture" and bool(settings.brave_search_api_key)


def build_search_provider(settings: Settings, catalogue: list[Lead]) -> SearchProvider:
    """
    Built once per process, not once per search: the rate limit Brave applies is
    per key, so every job has to queue behind the same limiter (spec §52).

    A fallback chain (spec §46) plugs in here — the pipeline asks a single
    `SearchProvider`, so a composite that tries Brave and then another provider
    needs no change above this function.
    """
    if not use_live_search(settings):
        return FixtureSearchProvider(catalogue)

    log.info(
        "live_search_enabled",
        extra={
            "provider": BraveSearchProvider.name,
            "results_per_query": settings.brave_results_per_query,
            "rate_limit_per_second": settings.brave_rate_limit_per_second,
        },
    )
    return BraveSearchProvider(
        settings.brave_search_api_key,
        endpoint=settings.brave_endpoint,
        results_per_query=settings.brave_results_per_query,
        timeout_seconds=settings.brave_timeout_seconds,
        rate_limit_per_second=settings.brave_rate_limit_per_second,
        safesearch=settings.brave_safesearch,
    )


def use_page_reading(settings: Settings) -> bool:
    return bool(settings.scrapegraph_api_key)


def use_browser_reading(settings: Settings) -> bool:
    """Our own browser reads real pages only: a catalogue's addresses do not exist."""
    return settings.browser_reader and use_live_search(settings)


@dataclass
class ReaderResources:
    """
    What the page readers must *not* duplicate per search: the connection pool, the
    rate limiter and the browser. The limit is a property of the API key (spec §52),
    so every concurrent search has to queue behind the same one — while the cost
    counters stay per search, which is why the extractor itself is built per job.
    """

    client: httpx.AsyncClient
    limiter: RateLimiter
    browser: BrowserPool | None = None

    async def aclose(self) -> None:
        await self.client.aclose()
        if self.browser is not None:
            await self.browser.aclose()


def build_reader_resources(settings: Settings) -> ReaderResources | None:
    if not (use_page_reading(settings) or use_browser_reading(settings)):
        return None
    return ReaderResources(
        client=httpx.AsyncClient(timeout=httpx.Timeout(settings.scrapegraph_timeout_seconds)),
        limiter=RateLimiter(settings.scrapegraph_rate_limit_per_second),
        browser=(
            BrowserPool(concurrency=settings.browser_concurrency)
            if use_browser_reading(settings)
            else None
        ),
    )


def build_post_reader(
    settings: Settings, resources: ReaderResources | None
) -> BrowserPageReader | None:
    """
    What opens an Instagram post to learn its author: our browser, or nothing.
    It never bills, so it needs no per-search counters and can be shared.
    """
    if resources is None or resources.browser is None:
        return None
    return BrowserPageReader(resources.browser, timeout_seconds=settings.browser_timeout_seconds)


def build_profile_extractor(
    settings: Settings,
    catalogue: list[Lead],
    repository: Repository | None = None,
    resources: ReaderResources | None = None,
) -> ProfileExtractor:
    """
    Built once per job, because the cost counters belong to one search.

    With a reader the stage becomes a chain — read, cached, with a stand-in behind
    it — assembled here so the pipeline still sees one extractor:

        FallbackProfileExtractor(            the page would not open → snippet
            RoutingPageReader(               Instagram, Facebook → our browser
                CachedPageReader(BrowserPageReader),
                CachedPageReader(            read it once (spec §53)
                    ScrapeGraphProfileExtractor(…))))   everything else

    Either reader may be missing (no ScrapeGraphAI key, browser switched off); the
    router then sends its platforms to the other or to the snippet. The cache needs
    a repository. Without one (a unit test, a script) the readers are used
    directly: correct, just not free the second time.
    """
    browser_pool = resources.browser if resources else None
    if not use_page_reading(settings) and browser_pool is None:
        if use_live_search(settings):
            # The catalogue is useless here: none of its URLs exist on the open web.
            return SnippetProfileExtractor()
        return FixtureProfileExtractor(catalogue)

    cost = ExtractionCost()

    def cached(reader: PageReader) -> PageReader:
        if repository is None:
            return reader
        return CachedPageReader(
            reader, repository, ttl_hours=settings.scrape_cache_ttl_hours, cost=cost
        )

    scrapegraph: PageReader | None = None
    if use_page_reading(settings):
        reader = ScrapeGraphProfileExtractor(
            settings.scrapegraph_api_key,
            endpoint=settings.scrapegraph_endpoint,
            timeout_seconds=settings.scrapegraph_timeout_seconds,
            rate_limit_per_second=settings.scrapegraph_rate_limit_per_second,
            credits_per_page=settings.scrapegraph_credits_per_page,
            stealth_credits=settings.scrapegraph_stealth_credits,
            stealth=settings.scrapegraph_stealth,
            page_wait_ms=settings.scrapegraph_page_wait_ms,
            cost=cost,
            # Per search, like the counters: a ceiling shared between searches would
            # mean the second one of the day silently gets nothing.
            budget=PageBudget(settings.max_pages_per_search),
            client=resources.client if resources else None,
            limiter=resources.limiter if resources else None,
        )
        scrapegraph = cached(reader)

    chain: PageReader = scrapegraph  # type: ignore[assignment]
    if browser_pool is not None:
        browser = BrowserPageReader(
            browser_pool, timeout_seconds=settings.browser_timeout_seconds, cost=cost
        )
        chain = RoutingPageReader(cached(browser), scrapegraph, cost=cost)

    log.info(
        "page_reading_enabled",
        extra={
            "reader": chain.name,
            "browser": browser_pool is not None,
            "cache_ttl_hours": settings.scrape_cache_ttl_hours,
            "fallback": settings.scrapegraph_fallback_to_snippets,
            "max_pages_per_search": settings.max_pages_per_search or "unlimited",
            "read_attempts": settings.scrapegraph_read_attempts,
            "stealth": settings.scrapegraph_stealth,
        },
    )
    if not settings.scrapegraph_fallback_to_snippets:
        return chain
    return FallbackProfileExtractor(
        chain,
        SnippetProfileExtractor(),
        # Not MAX_RETRIES: that limit is for calls that cost nothing to repeat. The
        # service bills a request it served, and our timeout does not un-bill it, so
        # a page is attempted once and then falls back to its snippet.
        attempts=settings.scrapegraph_read_attempts,
        cost=cost,
    )


def use_llm_signals(settings: Settings) -> bool:
    """The model judges signals only when asked to and able to — never by the key alone."""
    return settings.llm_signals and bool(settings.openai_api_key)


def build_signal_detector(settings: Settings) -> SignalDetector:
    if use_llm_signals(settings):
        return BudgetedSignalDetector(
            LlmSignalDetector(
                settings.openai_api_key,
                settings.openai_judge_model,
                endpoint=settings.openai_endpoint,
                timeout_seconds=settings.openai_timeout_seconds,
            ),
            settings.max_judgements_per_search,
        )
    return FixtureSignalDetector()


def build_brief_parser(settings: Settings) -> ResilientBriefParser:
    """
    The model when there is a key, the rules otherwise — and the rules again
    whenever the model fails, so a brief always comes back as something to review.
    """
    model = (
        OpenAIBriefParser(
            settings.openai_api_key,
            model=settings.openai_model,
            endpoint=settings.openai_endpoint,
            timeout_seconds=settings.openai_timeout_seconds,
        )
        if settings.openai_api_key
        else None
    )
    return ResilientBriefParser(model)


def stage_modes(settings: Settings) -> dict[str, str]:
    """Which adapter each pipeline stage is running, for `/health` (spec §21)."""
    return {
        "search": BraveSearchProvider.name if use_live_search(settings) else "fixture",
        "extraction": (
            ScrapeGraphProfileExtractor.name
            if use_page_reading(settings)
            else SnippetProfileExtractor.name
            if use_live_search(settings)
            else FixtureProfileExtractor.name
        ),
        "signals": (
            LlmSignalDetector.name if use_llm_signals(settings) else FixtureSignalDetector.name
        ),
    }


def pipeline_mode(settings: Settings) -> str:
    """
    `fixture` while nothing external is called, `live` once every stage has a real
    service behind it, and `partial` in between — which is where a workspace with a
    Brave and a ScrapeGraphAI key sits: real search, real page reading, and signals
    still detected by the keyword stand-in until Phase 6.
    """
    stages = stage_modes(settings)
    real = {
        stages["search"] != "fixture",
        stages["extraction"] == ScrapeGraphProfileExtractor.name,
        stages["signals"] == LlmSignalDetector.name,
    }
    if real == {True}:
        return "live"
    return "partial" if True in real else "fixture"
