"""
Reading as a stream, and not paying for what the search result already settles.

A measured live run took 5 min 51 s, and 4½ minutes of it were the same thing: the
candidates were read in waves of ten, each wave waited for its slowest page, and
the slowest page was always a LinkedIn profile at ScrapeGraphAI (20–60 s) while
our own browser had finished the wave's Instagram profiles in two seconds. Ten of
the twenty-two pages it paid for were the brand's own accounts — "Farmasi
Bucuresti", "FARMASI TUNISIE" — which the search result had already named.

These tests pin both fixes down with a reader that holds every paid page until the
test lets it go: under waves they would hang.
"""

import asyncio

import httpx
import pytest

from app.api.deps import close_container, open_container
from app.core.config import Settings
from app.models.common import Platform, SearchStatus
from app.models.rejection import RejectionReason
from app.models.search import Search, SearchCriteria
from app.models.source import DiscoveredUrl, UrlKind
from app.services.extraction import personhood
from app.services.extraction.signal_detector import FixtureSignalDetector
from app.services.scoring.scoring_service import ScoringService
from app.services.scraping.base import ExtractionCost, bills_for
from app.services.scraping.budget import PageBudget
from app.services.scraping.snippet_extractor import SnippetProfileExtractor
from app.services.search.pipeline import SearchPipeline
from app.services.search.providers.brave import BraveSearchProvider
from app.services.search.query_generator import TemplateQueryGenerator
from tests.test_live_search import WEB, live_criteria

pytestmark = pytest.mark.anyio

FREE = (Platform.INSTAGRAM, Platform.FACEBOOK)

#: The brand's own LinkedIn account, titled the way the measured run's were.
BRAND_ON_LINKEDIN = {
    "title": "MIHI Iberia Oficial - Distribuidor | LinkedIn",
    "url": "https://es.linkedin.com/in/mihi-iberia-oficial",
    "description": "Cosmética MIHI en España. Network marketing.",
    "language": "es",
}


class HeldReader:
    """
    Instagram and Facebook free and instant, like our browser; everything else
    paid, like ScrapeGraphAI — and held until the test releases it.
    """

    name = "held"

    def __init__(self, budget: int = 0) -> None:
        self.budget = PageBudget(budget)
        self.cost = ExtractionCost()
        self.release = asyncio.Event()
        self.started: list[str] = []
        self.finished: list[str] = []
        self._snippets = SnippetProfileExtractor()

    def bills(self, url: DiscoveredUrl) -> bool:
        return url.platform not in FREE

    async def extract(self, url: DiscoveredUrl):
        self.started.append(url.canonical_url)
        if self.bills(url):
            self.budget.take()
            await self.release.wait()
        profile = await self._snippets.extract(url)
        self.finished.append(url.canonical_url)
        return profile


def brave(extra: dict[str, list[dict]] | None = None):
    def handler(request: httpx.Request) -> httpx.Response:
        query = request.url.params.get("q", "")
        site = next((key for key in WEB if key and f"site:{key}" in query), "")
        results = WEB[site] + (extra or {}).get(site, [])
        return httpx.Response(200, json={"web": {"results": results}})

    return handler


async def start(settings: Settings, reader: HeldReader, *, extra=None, **criteria):
    container = await open_container(settings)
    search = Search(
        id="srch_stream",
        user_id=settings.dev_user_id,
        name="Streamed reading",
        status=SearchStatus.QUEUED,
        criteria=SearchCriteria.model_validate({**live_criteria(), **criteria}),
    )
    await container.repository.save_search(search)
    pipeline = SearchPipeline(
        repository=container.repository,
        settings=settings,
        query_generator=TemplateQueryGenerator(),
        provider=BraveSearchProvider(
            "test-token",
            client=httpx.AsyncClient(transport=httpx.MockTransport(brave(extra))),
            rate_limit_per_second=0,
        ),
        extractor=reader,
        detector=FixtureSignalDetector(),
        scoring=ScoringService(),
    )
    return container, search, asyncio.create_task(pipeline.run(search.id))


async def until(condition, *, seconds: float = 5.0) -> None:
    async def poll() -> None:
        while not condition():
            await asyncio.sleep(0.01)

    await asyncio.wait_for(poll(), seconds)


# ------------------------------------------------------------- the stream


async def test_a_slow_paid_page_does_not_hold_up_the_free_ones(settings):
    """
    Two paid pages (LinkedIn, a personal site) rank first and hang. Under waves of
    two, nothing behind them would ever start; streamed, every Instagram and
    Facebook profile is read while they wait.
    """
    reader = HeldReader()
    container, search, run = await start(
        settings.model_copy(update={"extraction_concurrency": 2}), reader
    )
    try:
        free = [url for url in WEB_URLS if _platform(url) in FREE]
        await until(lambda: all(url in reader.finished for url in free))

        assert not any(url in reader.finished for url in WEB_URLS if url not in free), (
            "the paid pages are still held, and the free ones did not wait for them"
        )
    finally:
        reader.release.set()
        await asyncio.wait_for(run, 5)
        await close_container(container)

    stored = await container_search(settings, search.id)
    assert stored.status is SearchStatus.COMPLETED


async def test_paid_reads_stay_within_the_concurrency_limit(settings):
    """Streaming is not unbounded: at most EXTRACTION_CONCURRENCY paid pages at once."""
    reader = HeldReader()
    container, _, run = await start(
        settings.model_copy(update={"extraction_concurrency": 1}), reader
    )
    try:
        await until(lambda: any(not _free(url) for url in reader.started))
        await asyncio.sleep(0.1)
        held = [url for url in reader.started if not _free(url)]
        assert len(held) == 1
    finally:
        reader.release.set()
        await asyncio.wait_for(run, 5)
        await close_container(container)


# ------------------------------------------------------ the search result decides


async def test_the_brands_own_account_is_refused_before_it_is_paid_for(settings):
    reader = HeldReader()
    reader.release.set()
    container, search, run = await start(
        settings, reader, extra={"linkedin.com": [BRAND_ON_LINKEDIN]}, brands=["MIHI"]
    )
    try:
        await asyncio.wait_for(run, 5)
        refused, _ = await container.repository.list_rejections(search.id)
    finally:
        await close_container(container)

    brand = "https://es.linkedin.com/in/mihi-iberia-oficial"
    assert brand not in reader.started, "a page the search result settled was paid for"
    assert "https://es.linkedin.com/in/pablo-serrano-mihi" in reader.started

    entry = next(item for item in refused if item.canonical_url == brand)
    assert entry.reason is RejectionReason.NOT_A_PERSON
    assert entry.read is False
    assert "never opened or paid for" in entry.detail


async def test_a_free_page_is_read_whatever_its_title_says(settings):
    """`MIHI España` on Instagram costs nothing to open, so the page gets the say."""
    reader = HeldReader()
    reader.release.set()
    container, _, run = await start(settings, reader, brands=["MIHI"])
    try:
        await asyncio.wait_for(run, 5)
    finally:
        await close_container(container)

    assert "https://instagram.com/mihi.oficial" in reader.started


# ------------------------------------------------------------ the rule itself


@pytest.mark.parametrize(
    "name",
    ["Farmasi Bucuresti", "FARMASI TUNISIE", "FarmaSI US Nicaragua", "Farmasi", "J'erelia Italia"],
)
def test_a_name_that_opens_with_the_searched_brand_is_the_brand(name):
    verdict = personhood.before_reading(name, ["Farmasi", "J’erelia"])
    assert not verdict.is_person
    assert "brand being searched for" in verdict.detail


@pytest.mark.parametrize(
    "name",
    [
        "Elizabeth Fairris",
        "Anna Koval - Farmasi",  # the brand after the name is a person's headline
        "Farmasiya Ivanova",  # a prefix, not the word
        "Наталья Гергела",
        "",
    ],
)
def test_a_person_survives_the_search_result_check(name):
    assert personhood.before_reading(name, ["Farmasi"]).is_person


def test_an_organisations_own_noun_needs_no_brand_to_give_it_away():
    assert not personhood.before_reading("Beauty Network Official", []).is_person
    assert not personhood.before_reading("Kosmetik GmbH", []).is_person


def test_only_the_name_is_judged_not_the_headline():
    """'We are hiring' in a real person's snippet is what LinkedIn's rule forgives."""
    assert personhood.before_reading("Marta Nowak", ["MIHI"]).is_person


def test_the_chain_says_which_reads_cost_money():
    class Paid:
        budget = PageBudget(5)

    class Free:
        pass

    url = DiscoveredUrl(
        url="https://linkedin.com/in/x",
        canonical_url="https://linkedin.com/in/x",
        platform=Platform.LINKEDIN,
        kind=UrlKind.CANDIDATE,
        title="X - Farmasi | LinkedIn",
        snippet="",
        query="",
        provider="test",
    )
    assert bills_for(Paid(), url)
    assert not bills_for(Free(), url)
    assert not bills_for(HeldReader(), url.model_copy(update={"platform": Platform.INSTAGRAM}))


# ----------------------------------------------------------------- helpers


def _platform(url: str) -> Platform:
    for platform in Platform:
        if f"{platform.value}.com" in url:
            return platform
    return Platform.WEBSITE


def _free(url: str) -> bool:
    return _platform(url) in FREE


#: The candidate addresses the canned results produce, canonicalized.
WEB_URLS = [
    "https://instagram.com/lucia.mihi",
    "https://instagram.com/mihi.oficial",
    "https://es.linkedin.com/in/pablo-serrano-mihi",
    "https://facebook.com/rosa.delgado.mlm",
    "https://luciaferrer.es/sobre-mi",
]


async def container_search(settings: Settings, search_id: str):
    container = await open_container(settings)
    try:
        return await container.repository.get_search(search_id)
    finally:
        await close_container(container)
