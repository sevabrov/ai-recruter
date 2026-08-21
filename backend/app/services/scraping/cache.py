"""
The scrape cache (spec §53).

    URL → cache hit? → serve it        (no request, no credit)
        → miss       → read it, store what happened

"Do not repeatedly scrape the same URL." The same Instagram profile is returned by
four of a search's twelve queries, and by tomorrow's search again — reading it once
is the difference between a demo and something a business can afford to run.

What is cached is the *outcome*, not just the profile: "this page is a shop" and
"this page will not open" are answers about the page and are reused. A reader
failing is not — a service that was down for a minute must not make a URL
unreadable for a week — so those attempts are recorded and never served.

Two guards worth naming:

* an entry is only reused by the reader that wrote it, so a better extractor never
  inherits a worse one's verdicts;
* a hit returns the profile as it was read, including the source page it came from.
  A later search that found the same URL through a different query gets the page's
  own words rather than that query's snippet, which is what we want: the profile is
  a property of the page.
"""

from datetime import UTC, datetime

from app.core.logging import get_logger
from app.db.repository import Repository
from app.models.profile import ExtractedProfile
from app.models.scrape import ScrapeOutcome, ScrapeRecord
from app.models.source import DiscoveredUrl
from app.services.scraping.base import ExtractionCost, PageRead, PageReader

log = get_logger(__name__)


class CachedPageReader(PageReader):
    def __init__(
        self,
        inner: PageReader,
        repository: Repository,
        *,
        ttl_hours: int,
        cost: ExtractionCost | None = None,
    ) -> None:
        self.inner = inner
        # The chain reports as the reader behind it: `/health` and every log line
        # should name what is doing the reading, not the cache in front of it.
        self.name = inner.name
        self.repo = repository
        self.ttl_hours = ttl_hours
        self.cost = cost or getattr(inner, "cost", None) or ExtractionCost()
        # Passed through, not owned: the pipeline asks the chain how much it may
        # still spend, and the answer belongs to the reader at the bottom of it.
        self.budget = getattr(inner, "budget", None)

    async def extract(self, url: DiscoveredUrl) -> ExtractedProfile | None:
        return (await self.read(url)).profile

    async def read(self, url: DiscoveredUrl) -> PageRead:
        stored = await self.repo.get_scrape(url.canonical_url)
        if stored and stored.reusable(self.ttl_hours, self.name):
            self.cost.pages_cached += 1
            log.info(
                "scrape_cache_hit",
                extra={"url": url.canonical_url, "outcome": stored.outcome.value},
            )
            return PageRead(
                outcome=stored.outcome,
                profile=stored.profile,
                content_hash=stored.content_hash,
                detail=stored.detail,
            )

        try:
            read = await self.inner.read(url)
        except Exception as error:
            # Recorded, not cached: the count is what tells the operator that a
            # platform or a provider is failing (Milestone 5).
            await self._store(url, PageRead(ScrapeOutcome.FAILED, detail=str(error)), stored)
            raise

        if read.outcome is ScrapeOutcome.SKIPPED:
            # The page was never opened — the search had spent its budget. Storing
            # that would count an attempt that never happened and make the platform
            # look unreadable in `GET /sources`.
            return read

        await self._store(url, read, stored)
        return read

    async def aclose(self) -> None:
        closer = getattr(self.inner, "aclose", None)
        if closer is not None:
            await closer()

    async def _store(
        self, url: DiscoveredUrl, read: PageRead, previous: ScrapeRecord | None
    ) -> None:
        now = datetime.now(UTC)
        await self.repo.save_scrape(
            ScrapeRecord(
                canonical_url=url.canonical_url,
                url=url.url,
                platform=url.platform,
                reader=self.name,
                outcome=read.outcome,
                content_hash=read.content_hash,
                detail=read.detail,
                attempts=(previous.attempts if previous else 0) + 1,
                profile=read.profile,
                first_seen_at=previous.first_seen_at if previous else now,
                last_scraped_at=now,
            )
        )
