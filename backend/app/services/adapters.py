"""
Adapter wiring — the one place that answers "what is plugged in right now?".

Selection is by configuration (spec §46–47): a provider is used when its key is
set, otherwise a stand-in keeps the product working and `/health` says which is
which, so nobody mistakes demo output for live results.

The stand-ins are not interchangeable, and the choice of extractor depends on the
search above it:

* fixture search + fixture extraction — the demo. Searches rediscover the seeded
  catalogue and re-score it against the criteria.
* **live search + snippet extraction** — Phase 4. Real URLs, and profiles built
  from the result metadata the search API returned, because a live search that
  reported nothing would be worse than the demo. Never invented from the
  catalogue: with a Brave key set, the seeded people are unreachable.
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
from app.services.extraction.signal_detector import (
    FixtureSignalDetector,
    LlmSignalDetector,
    SignalDetector,
)
from app.services.scraping.base import ExtractionCost, ProfileExtractor
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
    `SEARCH_PROVIDER=fixture` forces the demo even with a key configured, which is
    what the test suite and an offline demo use. Anything else means "live if we
    can": a key is required, never assumed.
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


@dataclass
class ReaderResources:
    """
    What the page reader must *not* duplicate per search: the connection pool and
    the rate limiter. The limit is a property of the API key (spec §52), so every
    concurrent search has to queue behind the same one — while the cost counters
    stay per search, which is why the extractor itself is still built per job.
    """

    client: httpx.AsyncClient
    limiter: RateLimiter

    async def aclose(self) -> None:
        await self.client.aclose()


def build_reader_resources(settings: Settings) -> ReaderResources | None:
    if not use_page_reading(settings):
        return None
    return ReaderResources(
        client=httpx.AsyncClient(timeout=httpx.Timeout(settings.scrapegraph_timeout_seconds)),
        limiter=RateLimiter(settings.scrapegraph_rate_limit_per_second),
    )


def build_profile_extractor(
    settings: Settings,
    catalogue: list[Lead],
    repository: Repository | None = None,
    resources: ReaderResources | None = None,
) -> ProfileExtractor:
    """
    Built once per job, because the cost counters belong to one search.

    With a ScrapeGraphAI key the stage becomes a chain — read, cached, with a
    stand-in behind it — assembled here so the pipeline still sees one extractor:

        FallbackProfileExtractor(          the page would not open → snippet
            CachedPageReader(              read it once (spec §53)
                ScrapeGraphProfileExtractor(…)))

    The cache needs a repository. Without one (a unit test, a script) the reader is
    used directly: correct, just not free the second time.
    """
    if not use_page_reading(settings):
        if use_live_search(settings):
            # The catalogue is useless here: none of its URLs exist on the open web.
            return SnippetProfileExtractor()
        return FixtureProfileExtractor(catalogue)

    cost = ExtractionCost()
    reader = ScrapeGraphProfileExtractor(
        settings.scrapegraph_api_key,
        endpoint=settings.scrapegraph_endpoint,
        timeout_seconds=settings.scrapegraph_timeout_seconds,
        rate_limit_per_second=settings.scrapegraph_rate_limit_per_second,
        cost=cost,
        client=resources.client if resources else None,
        limiter=resources.limiter if resources else None,
    )
    log.info(
        "page_reading_enabled",
        extra={
            "reader": reader.name,
            "cache_ttl_hours": settings.scrape_cache_ttl_hours,
            "fallback": settings.scrapegraph_fallback_to_snippets,
        },
    )

    cached: ScrapeGraphProfileExtractor | CachedPageReader = reader
    if repository is not None:
        cached = CachedPageReader(
            reader, repository, ttl_hours=settings.scrape_cache_ttl_hours, cost=cost
        )
    if not settings.scrapegraph_fallback_to_snippets:
        return cached
    return FallbackProfileExtractor(
        cached,
        SnippetProfileExtractor(),
        attempts=settings.max_retries,
        cost=cost,
    )


def build_signal_detector(settings: Settings) -> SignalDetector:
    if settings.openai_api_key:
        return LlmSignalDetector(settings.openai_api_key)
    return FixtureSignalDetector()


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
            LlmSignalDetector.name if settings.openai_api_key else FixtureSignalDetector.name
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
