"""
What to do when a page will not be read.

Milestone 5 is explicit: *"Do not assume every social-network URL can be
scraped."* Instagram shows a login wall to a datacentre IP more often than not,
Facebook shows a consent screen, LinkedIn depends on the day. A pipeline that
treated those as failures would find real people and report fewer of them than
Phase 4 did, which would be a regression dressed up as progress.

So the extraction stage is a chain:

    page reader (ScrapeGraphAI, cached)
        ↓ the page opened      → the profile the page states
        ↓ the page is a shop   → nothing, and that is final
        ↓ the page would not open, or the reader failed
    search-snippet extractor   → the profile the search result supports

The chain never invents anything. Which of the two produced a given profile is
recorded on it (`ExtractedProfile.extractor`), the outcome per platform is counted
in the scrape cache, and `GET /sources` reports both — so "we read the page" and
"we only saw the search result" are always distinguishable after the fact.

One more thing this class owns: a rejected key or an empty balance stops the reader
for the rest of the search instead of costing one refused request per URL (spec
§51 — an error that says "this will fail again" is not repeated).
"""

from app.core.errors import ProviderAuthError, ProviderError
from app.core.logging import get_logger
from app.core.retry import retry_async
from app.models.profile import ExtractedProfile
from app.models.scrape import ScrapeOutcome
from app.models.source import DiscoveredUrl
from app.services.scraping.base import ExtractionCost, PageRead, PageReader, ProfileExtractor

log = get_logger(__name__)


class FallbackProfileExtractor(ProfileExtractor):
    def __init__(
        self,
        reader: PageReader,
        stand_in: ProfileExtractor,
        *,
        attempts: int = 3,
        cost: ExtractionCost | None = None,
    ) -> None:
        self.reader = reader
        self.stand_in = stand_in
        # The stage is named after what is meant to be doing the work.
        self.name = reader.name
        self.attempts = attempts
        self.cost = cost or getattr(reader, "cost", None) or ExtractionCost()
        #: Set once the provider has told us the key itself is the problem.
        self._reader_disabled: str | None = None

    async def extract(self, url: DiscoveredUrl) -> ExtractedProfile | None:
        read = await self._read(url)

        if read.usable:
            return read.profile
        if read.outcome is ScrapeOutcome.NOT_A_PERSON:
            # The page was read and settled the question. The snippet does not get
            # a second vote — that is how shops come back as leads.
            return None

        profile = await self.stand_in.extract(url)
        log.info(
            "extraction_fell_back",
            extra={
                "url": url.canonical_url,
                "platform": url.platform.value,
                "outcome": read.outcome.value,
                "recovered": profile is not None,
            },
        )
        return profile

    async def _read(self, url: DiscoveredUrl) -> PageRead:
        """
        Never raises: extraction failing on one URL may cost that lead its page, but
        it may not fail the search (spec §51's "invalid extraction" and "blocked
        page" are expected states, not errors).
        """
        if self._reader_disabled:
            return PageRead(ScrapeOutcome.FAILED, detail=self._reader_disabled)

        try:
            return await retry_async(
                lambda: self.reader.read(url),
                attempts=self.attempts,
                label=f"read:{self.reader.name}",
            )
        except ProviderAuthError as error:
            self._disable(error)
            return PageRead(ScrapeOutcome.FAILED, detail=error.message)
        except ProviderError as error:
            # A refused request with nothing retryable about it: if the balance is
            # empty, every other URL in this search would be refused too.
            if not error.retryable:
                self._disable(error)
            return PageRead(ScrapeOutcome.FAILED, detail=error.message)
        except Exception as error:
            log.warning(
                "page_read_failed",
                extra={"url": url.canonical_url, "error": type(error).__name__},
            )
            return PageRead(ScrapeOutcome.FAILED, detail=str(error))

    def _disable(self, error: ProviderError) -> None:
        self._reader_disabled = error.message
        log.error(
            "page_reader_disabled",
            extra={"reader": self.reader.name, "code": error.code, "reason": error.message},
        )
