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
* live search + ScrapeGraphAI — Phase 5, when the extractor can read the page.
"""

from app.core.config import Settings
from app.core.logging import get_logger
from app.models.lead import Lead
from app.services.extraction.signal_detector import (
    FixtureSignalDetector,
    LlmSignalDetector,
    SignalDetector,
)
from app.services.scraping.base import ProfileExtractor
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


def build_profile_extractor(settings: Settings, catalogue: list[Lead]) -> ProfileExtractor:
    if settings.scrapegraph_api_key:
        return ScrapeGraphProfileExtractor(settings.scrapegraph_api_key)
    if use_live_search(settings):
        # The catalogue is useless here: none of its URLs exist on the open web.
        return SnippetProfileExtractor()
    return FixtureProfileExtractor(catalogue)


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
            if settings.scrapegraph_api_key
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
    service behind it, and `partial` in between — which is where Phase 4 leaves a
    workspace with a Brave key: real search, stand-in reading and judging.
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
