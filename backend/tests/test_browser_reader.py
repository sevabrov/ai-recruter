"""
Our own browser reader for Instagram and Facebook — without starting a browser.

What a page showed is fed straight into the verdict, so these tests pin down what
the reader makes of it: who the person is, what counts as gone, as a wall, and
where each platform is routed.
"""

import asyncio

import httpx

from app.core.config import Settings
from app.core.limits import RateLimiter
from app.models.common import Platform
from app.models.scrape import ScrapeOutcome
from app.models.source import DiscoveredUrl, UrlKind
from app.services.adapters import ReaderResources, build_profile_extractor
from app.services.scraping.base import PROFILE_GONE, ExtractionCost, PageRead, fetch_from
from app.services.scraping.browser_reader import (
    BrowserPageReader,
    BrowserPool,
    RoutingPageReader,
)
from app.services.scraping.cache import CachedPageReader
from app.services.scraping.fallback import FallbackProfileExtractor
from app.services.scraping.snippet_extractor import SnippetProfileExtractor


def _url(address: str, platform: Platform, title: str = "", snippet: str = "") -> DiscoveredUrl:
    return DiscoveredUrl(
        url=address,
        canonical_url=address.rstrip("/"),
        platform=platform,
        kind=UrlKind.CANDIDATE,
        title=title,
        snippet=snippet,
        query="test",
        provider="test",
    )


def _seen(title: str, header: str = "", description: str = "", final_url: str = "") -> dict:
    return {
        "title": title,
        "header": header,
        "description": description,
        "final_url": final_url or "https://www.instagram.com/x/",
    }


def _verdict(url: DiscoveredUrl, seen: dict) -> PageRead:
    reader = BrowserPageReader(pool=None, cost=ExtractionCost())  # type: ignore[arg-type]
    return asyncio.run(reader._verdict(url, seen))


IRISKA = _url(
    "https://www.instagram.com/iriska.kononova/",
    Platform.INSTAGRAM,
    title="Ірина (@iriska.kononova) • Instagram photos and videos",
    snippet="MLM-ментор",
)


def test_the_whole_bio_becomes_the_profile_and_the_search_result_stays_its_source():
    seen = _seen(
        "MLM-ментор | Мотивація (@iriska.kononova) • Instagram photos and videos",
        header=(
            "iriska.kononova\n905 followers\n447 following\nMLM-ментор | Мотивація\n"
            "✨️ Лідер CHOICE\n💫Тут про сім'ю, бізнес, подорожі\nЛьвів"
        ),
    )

    read = _verdict(IRISKA, seen)

    assert read.outcome is ScrapeOutcome.OK
    profile = read.profile
    assert profile is not None
    assert profile.extractor == "browser"
    assert "Лідер CHOICE" in (profile.summary or "")
    assert profile.platforms[0].followers == 905
    # What the search engine said is kept as the source, not replaced by the page.
    assert profile.sources[0].snippet == "MLM-ментор"
    assert profile.location.country == "Ukraine"  # "Львів"


def test_a_profile_that_no_longer_exists_is_gone_not_a_lead():
    read = _verdict(IRISKA, _seen("Profile isn't available • Instagram"))

    assert read.outcome is ScrapeOutcome.NOT_A_PERSON
    assert read.detail == PROFILE_GONE


def test_a_login_wall_is_a_wall_not_a_verdict_about_the_person():
    read = _verdict(
        IRISKA,
        _seen("Instagram", final_url="https://www.instagram.com/accounts/login/?next=x"),
    )

    assert read.outcome is ScrapeOutcome.BLOCKED


def test_a_community_page_on_facebook_names_no_person():
    page = _url("https://www.facebook.com/delobmd21", Platform.FACEBOOK, title="Делай свое дело")
    seen = _seen(
        "Делай свое дело | Facebook",
        header="Делай свое дело\n32 followers\nPage · Community",
        description="Делай свое дело. 32 followers. Мы верим, что каждый человек…",
        final_url="https://www.facebook.com/delobmd21",
    )

    assert _verdict(page, seen).outcome is ScrapeOutcome.NOT_A_PERSON


class _Reader:
    def __init__(self, name: str) -> None:
        self.name = name
        self.asked: list[str] = []

    async def read(self, url: DiscoveredUrl) -> PageRead:
        self.asked.append(url.url)
        return PageRead(ScrapeOutcome.FAILED, detail="test")


def test_instagram_and_facebook_go_to_the_browser_and_linkedin_does_not():
    browser, other = _Reader("browser"), _Reader("scrapegraph")
    router = RoutingPageReader(browser, other, cost=ExtractionCost())

    for address, platform in (
        ("https://www.instagram.com/a/", Platform.INSTAGRAM),
        ("https://www.facebook.com/b", Platform.FACEBOOK),
        ("https://www.linkedin.com/in/c/", Platform.LINKEDIN),
    ):
        asyncio.run(router.read(_url(address, platform)))

    assert browser.asked == ["https://www.instagram.com/a/", "https://www.facebook.com/b"]
    assert other.asked == ["https://www.linkedin.com/in/c/"]
    # The chain reports, and bills, as the reader that costs money.
    assert router.name == "scrapegraph"


class _Gone:
    name = "browser"
    cost = ExtractionCost()

    async def read(self, url: DiscoveredUrl) -> PageRead:
        return PageRead(ScrapeOutcome.NOT_A_PERSON, detail=PROFILE_GONE)


def test_a_deleted_profile_is_not_rebuilt_from_its_old_search_result():
    """Six of fifty addresses in one run no longer existed; the index still had them."""
    named = _url(
        "https://www.instagram.com/marija.mikhailova/",
        Platform.INSTAGRAM,
        title="Мария Михайлова (@marija.mikhailova) • Instagram photos and videos",
        snippet="Сетевой бизнес",
    )
    chain = FallbackProfileExtractor(_Gone(), SnippetProfileExtractor())

    assert asyncio.run(chain.extract(named)) is None
    # …and the refusal can say so, rather than "a brand account, a community or a shop".
    assert named.canonical_url in chain.gone


def test_the_country_reaches_scrapegraph_past_the_router():
    """
    `fetch_from` used to follow `inner` and `reader` only, and stopped at the
    router — so with our own browser on, ScrapeGraphAI never heard which country to
    fetch LinkedIn through. Built the way the container builds it, cache included.
    """
    settings = Settings(
        scrapegraph_api_key="key",
        brave_search_api_key="key",
        search_provider="brave",
        browser_reader=True,
        openai_api_key="",
    )
    resources = ReaderResources(
        client=httpx.AsyncClient(), limiter=RateLimiter(0), browser=BrowserPool(concurrency=1)
    )
    chain = build_profile_extractor(settings, [], repository=object(), resources=resources)  # type: ignore[arg-type]

    fetch_from(chain, "UA")

    router = chain.reader
    assert isinstance(router, RoutingPageReader)
    assert isinstance(router.other, CachedPageReader)
    assert router.other.inner.country == "UA"
