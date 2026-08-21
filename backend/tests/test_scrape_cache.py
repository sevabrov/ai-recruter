"""
The scrape cache and the source record (spec §53, Milestone 5).

Two things are being tested, and they are the same rows:

* **a page is read once.** Credits are money, and the same profile URL comes back
  from four queries today and from tomorrow's search again.
* **what reading yielded is remembered per platform.** The milestone asks for the
  record explicitly, because "we found nobody on Instagram" and "Instagram would
  not let us in" are different problems with different answers.

The reader below is a stand-in that counts calls: what matters here is how often the
thing behind the cache is asked, not what it returns.
"""

from contextlib import asynccontextmanager, suppress
from datetime import UTC, datetime, timedelta

from app.api.deps import close_container, open_container
from app.models.common import Platform
from app.models.profile import ExtractedProfile
from app.models.scrape import ScrapeOutcome, ScrapeRecord
from app.models.source import DiscoveredUrl, UrlKind
from app.services.scraping.base import ExtractionCost, PageRead, PageReader
from app.services.scraping.cache import CachedPageReader

READER = "scrapegraph"

INSTAGRAM = DiscoveredUrl(
    url="https://www.instagram.com/lucia.mihi/?utm_source=brave",
    canonical_url="https://instagram.com/lucia.mihi",
    platform=Platform.INSTAGRAM,
    kind=UrlKind.CANDIDATE,
    title="Lucía Ferrer (@lucia.mihi) • Instagram",
    snippet="network marketing y belleza",
    query="site:instagram.com MIHI Spain",
    provider="brave",
)


def profile_for(url: DiscoveredUrl, name: str = "Lucía Ferrer") -> ExtractedProfile:
    return ExtractedProfile(
        url=url.url,
        canonical_url=url.canonical_url,
        platform=url.platform,
        name=name,
        headline="Líder de equipo",
        extractor=READER,
    )


def elsewhere(canonical: str, platform: Platform) -> DiscoveredUrl:
    return INSTAGRAM.model_copy(
        update={"canonical_url": canonical, "url": canonical, "platform": platform}
    )


class CountingReader(PageReader):
    """Answers with whatever it was handed, and remembers being asked."""

    name = READER

    def __init__(self, *answers: PageRead | Exception) -> None:
        self.answers = list(answers)
        self.calls: list[str] = []
        self.cost = ExtractionCost()

    async def read(self, url: DiscoveredUrl) -> PageRead:
        self.calls.append(url.canonical_url)
        answer = self.answers[min(len(self.calls) - 1, len(self.answers) - 1)]
        if isinstance(answer, Exception):
            raise answer
        self.cost.pages_read += 1
        self.cost.credits += 1
        return answer

    async def extract(self, url: DiscoveredUrl) -> ExtractedProfile | None:
        return (await self.read(url)).profile


@asynccontextmanager
async def workspace(settings):
    """The app's own startup path, so the cache runs against the real schema."""
    container = await open_container(settings)
    try:
        yield container.repository
    finally:
        await close_container(container)


def cached(inner: PageReader, repository, ttl_hours: int = 168) -> CachedPageReader:
    return CachedPageReader(inner, repository, ttl_hours=ttl_hours, cost=inner.cost)


# ------------------------------------------------------------------ reading once


async def test_the_same_page_is_read_once_however_often_it_is_found(settings):
    ok = PageRead(ScrapeOutcome.OK, profile_for(INSTAGRAM), content_hash="abc")
    inner = CountingReader(ok)

    async with workspace(settings) as repository:
        reader = cached(inner, repository)

        first = await reader.read(INSTAGRAM)
        second = await reader.read(INSTAGRAM)

    assert inner.calls == [INSTAGRAM.canonical_url]  # the second read cost nothing
    assert first.profile and second.profile
    assert second.profile.name == "Lucía Ferrer"
    assert second.content_hash == "abc"
    assert (reader.cost.pages_read, reader.cost.pages_cached) == (1, 1)


async def test_a_cached_profile_survives_the_round_trip_through_the_database(settings):
    stored = profile_for(INSTAGRAM)
    stored.observations = []
    inner = CountingReader(PageRead(ScrapeOutcome.OK, stored))

    async with workspace(settings) as repository:
        reader = cached(inner, repository)
        await reader.read(INSTAGRAM)
        # A different search, a different extractor instance, the same page.
        again = await cached(CountingReader(PageRead(ScrapeOutcome.OK, stored)), repository).read(
            INSTAGRAM
        )

    assert again.profile is not None
    assert again.profile.canonical_url == INSTAGRAM.canonical_url
    assert again.profile.extractor == READER
    assert again.profile.headline == "Líder de equipo"


async def test_tracking_parameters_do_not_buy_a_second_read(settings):
    """One canonical URL is one entry (spec §31 normalises, §53 caches)."""
    inner = CountingReader(PageRead(ScrapeOutcome.OK, profile_for(INSTAGRAM)))
    same_page = INSTAGRAM.model_copy(update={"url": "https://instagram.com/lucia.mihi/?igshid=9"})

    async with workspace(settings) as repository:
        reader = cached(inner, repository)
        await reader.read(INSTAGRAM)
        await reader.read(same_page)

    assert len(inner.calls) == 1


async def test_a_url_too_long_for_an_index_is_still_cached(settings):
    """The row's key is a hash, so a profile link with a query string cannot break it."""
    long_url = "https://example.com/profile?" + "&".join(f"p{i}=value" for i in range(200))
    url = elsewhere(long_url, Platform.WEBSITE)
    inner = CountingReader(PageRead(ScrapeOutcome.OK, profile_for(url, "Long Url")))

    async with workspace(settings) as repository:
        reader = cached(inner, repository)
        await reader.read(url)
        hit = await reader.read(url)

    assert len(inner.calls) == 1
    assert hit.profile is not None and hit.profile.name == "Long Url"


# ------------------------------------------------------- what is worth remembering


async def test_a_page_that_would_not_open_is_not_asked_again(settings):
    """
    The most valuable entry in the cache: Instagram's login wall costs one credit,
    once, instead of one per search per URL.
    """
    inner = CountingReader(PageRead(ScrapeOutcome.BLOCKED, detail="login wall"))

    async with workspace(settings) as repository:
        reader = cached(inner, repository)
        await reader.read(INSTAGRAM)
        again = await reader.read(INSTAGRAM)

    assert len(inner.calls) == 1
    assert again.outcome is ScrapeOutcome.BLOCKED
    assert again.profile is None
    assert again.detail == "login wall"


async def test_a_shop_stays_a_shop(settings):
    inner = CountingReader(PageRead(ScrapeOutcome.NOT_A_PERSON, detail="Tienda MIHI"))

    async with workspace(settings) as repository:
        reader = cached(inner, repository)
        await reader.read(INSTAGRAM)
        again = await reader.read(INSTAGRAM)

    assert len(inner.calls) == 1
    assert again.outcome is ScrapeOutcome.NOT_A_PERSON


async def test_a_reader_that_failed_is_recorded_but_never_served(settings):
    """
    A service down for a minute must not make a URL unreadable for a week — so the
    attempt is stored (the operator needs the count) and the next search tries again.
    """
    inner = CountingReader(
        RuntimeError("connection reset"), PageRead(ScrapeOutcome.OK, profile_for(INSTAGRAM))
    )

    async with workspace(settings) as repository:
        reader = cached(inner, repository)
        with suppress(RuntimeError):
            await reader.read(INSTAGRAM)
        recorded = await repository.get_scrape(INSTAGRAM.canonical_url)

        second = await reader.read(INSTAGRAM)
        after = await repository.get_scrape(INSTAGRAM.canonical_url)

    assert recorded is not None and recorded.outcome is ScrapeOutcome.FAILED
    assert recorded.detail and "connection reset" in recorded.detail
    assert len(inner.calls) == 2  # tried again, as it should be
    assert second.outcome is ScrapeOutcome.OK
    assert after is not None and after.attempts == 2  # the history is kept


async def test_an_entry_older_than_the_ttl_is_read_again(settings):
    inner = CountingReader(PageRead(ScrapeOutcome.OK, profile_for(INSTAGRAM)))

    async with workspace(settings) as repository:
        await repository.save_scrape(
            ScrapeRecord(
                canonical_url=INSTAGRAM.canonical_url,
                url=INSTAGRAM.url,
                platform=INSTAGRAM.platform,
                reader=READER,
                outcome=ScrapeOutcome.OK,
                profile=profile_for(INSTAGRAM, "Stale Copy"),
                first_seen_at=datetime.now(UTC) - timedelta(days=30),
                last_scraped_at=datetime.now(UTC) - timedelta(days=30),
            )
        )
        read = await cached(inner, repository, ttl_hours=24).read(INSTAGRAM)

    assert len(inner.calls) == 1
    assert read.profile is not None and read.profile.name == "Lucía Ferrer"


async def test_a_ttl_of_zero_turns_the_cache_off_without_losing_the_record(settings):
    inner = CountingReader(PageRead(ScrapeOutcome.OK, profile_for(INSTAGRAM)))

    async with workspace(settings) as repository:
        reader = cached(inner, repository, ttl_hours=0)
        await reader.read(INSTAGRAM)
        await reader.read(INSTAGRAM)
        entry = await repository.get_scrape(INSTAGRAM.canonical_url)

    assert len(inner.calls) == 2
    assert entry is not None and entry.attempts == 2


async def test_another_readers_verdict_is_not_inherited(settings):
    """A better extractor must not be handed a worse one's conclusions."""
    inner = CountingReader(PageRead(ScrapeOutcome.OK, profile_for(INSTAGRAM)))

    async with workspace(settings) as repository:
        await repository.save_scrape(
            ScrapeRecord(
                canonical_url=INSTAGRAM.canonical_url,
                url=INSTAGRAM.url,
                platform=INSTAGRAM.platform,
                reader="some-older-reader",
                outcome=ScrapeOutcome.BLOCKED,
            )
        )
        read = await cached(inner, repository).read(INSTAGRAM)

    assert len(inner.calls) == 1
    assert read.outcome is ScrapeOutcome.OK


# ------------------------------------------------------------- the source record


async def test_the_source_record_says_which_platforms_can_be_read(settings):
    linkedin = elsewhere("https://linkedin.com/in/pablo-serrano", Platform.LINKEDIN)
    website = elsewhere("https://luciaferrer.es", Platform.WEBSITE)
    other_gram = elsewhere("https://instagram.com/rosa.mlm", Platform.INSTAGRAM)

    async with workspace(settings) as repository:
        await cached(
            CountingReader(PageRead(ScrapeOutcome.BLOCKED, detail="login")), repository
        ).read(INSTAGRAM)
        await cached(
            CountingReader(PageRead(ScrapeOutcome.BLOCKED, detail="login")), repository
        ).read(other_gram)
        await cached(
            CountingReader(PageRead(ScrapeOutcome.OK, profile_for(linkedin, "Pablo Serrano"))),
            repository,
        ).read(linkedin)
        await cached(
            CountingReader(PageRead(ScrapeOutcome.OK, profile_for(website, "Lucía Ferrer"))),
            repository,
        ).read(website)

        report = {row.platform: row for row in await repository.source_reliability()}

    assert set(report) == {Platform.INSTAGRAM, Platform.LINKEDIN, Platform.WEBSITE}
    assert report[Platform.INSTAGRAM].pages == 2
    assert report[Platform.INSTAGRAM].blocked == 2
    assert report[Platform.INSTAGRAM].usable == 0
    assert report[Platform.INSTAGRAM].usable_share == 0.0
    assert report[Platform.LINKEDIN].usable == 1
    assert report[Platform.LINKEDIN].usable_share == 1.0
    assert report[Platform.WEBSITE].last_read_at is not None


async def test_the_source_record_counts_the_reader_failing_too(settings):
    async with workspace(settings) as repository:
        reader = cached(CountingReader(RuntimeError("timeout")), repository)
        with suppress(RuntimeError):
            await reader.read(INSTAGRAM)

        report = await repository.source_reliability()

    assert [(row.platform, row.failed, row.usable) for row in report] == [
        (Platform.INSTAGRAM, 1, 0)
    ]


async def test_nothing_read_yet_is_an_empty_record_not_a_perfect_one(settings):
    async with workspace(settings) as repository:
        assert await repository.source_reliability() == []


# ------------------------------------------------------------------- endpoints


def test_the_sources_endpoint_describes_the_stand_in_when_nothing_is_read(client):
    body = client.get("/sources").json()

    assert body["live"] is False
    assert body["reader"] == "fixture"
    assert body["cacheTtlHours"] == 168
    assert body["items"] == []
    assert "search results" in body["fallback"]


def test_a_demo_reset_keeps_the_pages_it_already_paid_for(client, settings):
    """
    Deliberate: `POST /admin/reset` puts the demo workspace back, and re-buying
    pages that were already read is not part of that (spec §53).
    """
    import asyncio

    url = elsewhere("https://instagram.com/kept.after.reset", Platform.INSTAGRAM)

    async def read_one() -> None:
        async with workspace(settings) as repository:
            await cached(
                CountingReader(PageRead(ScrapeOutcome.OK, profile_for(url, "Kept Lead"))),
                repository,
            ).read(url)

    asyncio.run(read_one())
    assert client.get("/sources").json()["items"], "the page should be on record"

    assert client.post("/admin/reset").status_code == 200

    after = client.get("/sources").json()["items"]
    assert [row["platform"] for row in after] == ["instagram"]
