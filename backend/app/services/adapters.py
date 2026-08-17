"""
Adapter wiring — the one place that answers "what is plugged in right now?".

Selection is by configuration (spec §46–47): a provider is used when its key is
set, otherwise the fixture stand-in keeps the product working and `/health`
reports `pipeline: "fixture"` so nobody mistakes demo output for live results.

Phase 4–6 consist of implementing the three real adapters; the choices below then
start returning them without any other file changing.
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
from app.services.search.providers.base import SearchProvider
from app.services.search.providers.brave import BraveSearchProvider
from app.services.search.providers.fixture import FixtureSearchProvider

log = get_logger(__name__)


def build_search_provider(settings: Settings, catalogue: list[Lead]) -> SearchProvider:
    if settings.search_provider == "brave" and settings.brave_search_api_key:
        return BraveSearchProvider(settings.brave_search_api_key)
    return FixtureSearchProvider(catalogue)


def build_profile_extractor(settings: Settings, catalogue: list[Lead]) -> ProfileExtractor:
    if settings.scrapegraph_api_key:
        return ScrapeGraphProfileExtractor(settings.scrapegraph_api_key)
    return FixtureProfileExtractor(catalogue)


def build_signal_detector(settings: Settings) -> SignalDetector:
    if settings.openai_api_key:
        return LlmSignalDetector(settings.openai_api_key)
    return FixtureSignalDetector()


def pipeline_mode(settings: Settings) -> str:
    """Reports `live` only when every stage has a real adapter behind it."""
    configured = all(
        (
            settings.brave_search_api_key,
            settings.scrapegraph_api_key,
            settings.openai_api_key,
        )
    )
    return "live" if configured else "fixture"
