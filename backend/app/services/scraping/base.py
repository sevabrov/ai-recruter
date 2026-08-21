"""
Extraction interfaces (spec §33–34).

Two protocols, one for each question the pipeline and the cache ask:

* `ProfileExtractor` — "give me the profile behind this URL, or nothing". That is
  all the pipeline ever needs: whether the page was read by ScrapeGraphAI, built
  from a search snippet or taken from a fixture is invisible to it, and `None` is a
  legitimate answer — blocked pages, empty pages and pages that turn out not to
  describe a person all end here rather than becoming a bad lead.
* `PageReader` — "read this page and tell me *what happened*". The cache and the
  fallback need the difference between "the page says this is a shop" and "the page
  would not open": one is a verdict worth storing for a week, the other is a
  service having a bad minute (spec §53, and Milestone 5's instruction to record
  which sources can be read at all).

Every page reader is also a profile extractor, so either can be plugged into the
pipeline directly.
"""

from dataclasses import dataclass
from typing import Protocol

from app.models.profile import ExtractedProfile
from app.models.scrape import ScrapeOutcome
from app.models.source import DiscoveredUrl
from app.services.scraping.budget import PageBudget


@dataclass
class ExtractionCost:
    """
    What the extraction stage spent, accumulated across one search (spec §54).

    Mutable and shared by the whole extractor chain: the reader counts requests and
    credits, the cache counts what it saved. The pipeline copies it into the
    search's usage, so the number the user sees is measured, not estimated.
    Extractors that read nothing (fixtures, snippets) leave it at zero, which is
    exactly right — they cost nothing.
    """

    pages_read: int = 0
    pages_cached: int = 0
    #: Candidate pages the search's budget refused to pay for. They still became
    #: leads, from their search snippet — the number is here so a thin result is
    #: explained by the limit rather than looking like a bad search.
    pages_skipped: int = 0
    #: Requests the service served, whatever came of them — including one that
    #: answered too late for us to use it. That is the number that maps onto the
    #: provider's own bill: a timeout on our side does not un-spend the credit,
    #: which is why `pages_read` (useful answers) is counted separately.
    paid_attempts: int = 0
    credits: int = 0
    #: What the extraction consumed, as the service reported it. Recorded and logged
    #: per search; Phase 6 is what puts token counts on the usage screen, because
    #: that is when the LLM stage starts spending them too (spec §54).
    tokens_in: int = 0
    tokens_out: int = 0


@dataclass
class PageRead:
    """The result of pointing a reader at one URL."""

    outcome: ScrapeOutcome
    profile: ExtractedProfile | None = None
    content_hash: str | None = None
    #: Short and safe to store: why the page could not be used. Never a key.
    detail: str | None = None

    @property
    def usable(self) -> bool:
        return self.outcome is ScrapeOutcome.OK and self.profile is not None


class ProfileExtractor(Protocol):
    name: str

    async def extract(self, url: DiscoveredUrl) -> ExtractedProfile | None:
        """Return the structured profile, or None if the page yields nothing usable."""
        ...


class PageReader(ProfileExtractor, Protocol):
    async def read(self, url: DiscoveredUrl) -> PageRead:
        """Read the page and classify the outcome, without raising for a bad page."""
        ...


def cost_of(extractor: object) -> ExtractionCost:
    """
    What this extractor chain spent. Extractors are free to have no cost at all —
    the fixture and snippet ones do not — so this never fails.
    """
    cost = getattr(extractor, "cost", None)
    return cost if isinstance(cost, ExtractionCost) else ExtractionCost()


def budget_of(extractor: object) -> PageBudget | None:
    """
    The paid-read ceiling this chain is under, if it has one. None means "nothing
    here costs money", which is the truth for the snippet and fixture extractors.

    The pipeline needs this to decide how many pages to *dispatch* at once: with one
    page left to pay for and ten coroutines in flight, the slot would go to whichever
    of them reached the reader first, and ranking the candidates would buy nothing.
    """
    budget = getattr(extractor, "budget", None)
    return budget if isinstance(budget, PageBudget) else None
