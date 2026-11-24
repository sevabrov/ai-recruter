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

import re

from app.core.errors import ProviderAuthError, ProviderError
from app.core.logging import get_logger
from app.core.retry import retry_async
from app.models.profile import ExtractedProfile
from app.models.scrape import ScrapeOutcome
from app.models.source import DiscoveredUrl
from app.services.scraping.base import (
    PROFILE_GONE,
    ExtractionCost,
    PageRead,
    PageReader,
    ProfileExtractor,
    bills_for,
)
from app.services.scraping.names import clean, commercial, looks_like_a_person

log = get_logger(__name__)


def titled_as_a_person(url: DiscoveredUrl) -> bool:
    """
    Whether the search result is titled with a person's name: "Sasha Barin
    (@barinsasha) • Instagram" yes, "MIHI España (@mihi.oficial)" no — business
    words are looked for in the name and the handle, not in the platform's own
    "• Instagram photos and videos".
    """
    title = url.title or ""
    name = clean(re.split(r"\s*\(@|\s+[•|·—–-]\s+", title, maxsplit=1)[0])
    # The platform's own words ("• Instagram photos and videos") are not the
    # account's: only the name and the handle are looked at for business words.
    handle = re.search(r"\(@([^)]+)\)", title)
    return looks_like_a_person(name) and not commercial(
        f"{name} {handle.group(1) if handle else ''}"
    )


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
        #: The reader's paid-page ceiling, passed through so the pipeline can see it.
        self.budget = getattr(reader, "budget", None)
        #: Set once the provider has told us the key itself is the problem.
        self._reader_disabled: str | None = None
        #: Addresses whose page never opened and were judged on the search result
        #: alone — so a refusal can say "would not open" rather than "was read".
        self.unread: set[str] = set()
        #: Addresses whose page said the profile no longer exists — so a refusal can
        #: say that, rather than "a brand account, a community or a shop".
        self.gone: set[str] = set()

    def bills(self, url: DiscoveredUrl) -> bool:
        """Only the reader can cost money; the snippet behind it never does."""
        return bills_for(self.reader, url)

    async def extract(self, url: DiscoveredUrl) -> ExtractedProfile | None:
        read = await self._read(url)
        self.unread.discard(url.canonical_url)

        if read.usable:
            return read.profile
        if read.outcome is ScrapeOutcome.NOT_A_PERSON and (
            read.detail == PROFILE_GONE or not titled_as_a_person(url)
        ):
            # The page was read and settled the question. The snippet does not get
            # a second vote — that is how shops come back as leads.
            #
            # "Gone" included, checked again: "Ewelina Kapinos" and "Klaudia
            # Koliber", both titled as people in a run's search results, open as
            # gone in the same browser that opens `avon_polska` fine — exactly as a
            # handle that never existed does. The index remembers them from 2018.
            if read.detail == PROFILE_GONE:
                self.gone.add(url.canonical_url)
            return None
        # …unless the search result itself is titled with a person's name. An
        # Instagram profile often serves a login wall to a reader: "no person on
        # this page" then means "nothing on this page", and "Артем Нестеренко
        # (@biznesnesterenko)" was refused as a brand. The snippet is judged
        # instead — by the same judge, which can still say it is not a person.

        profile = await self.stand_in.extract(url)
        if read.outcome is not ScrapeOutcome.NOT_A_PERSON:
            self.unread.add(url.canonical_url)
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
