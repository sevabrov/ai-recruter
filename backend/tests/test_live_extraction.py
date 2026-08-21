"""
URL → structured candidate JSON (spec §60, Milestone 5).

The milestone names the sources to test against, and this file uses all of them —
the canned web in `test_live_search.py` is a personal website, a public Instagram
profile, a public LinkedIn profile, a public Facebook profile, a brand account and
a shop:

    ┌ Brave (stubbed) ──→ real URLs ──→ ScrapeGraphAI (stubbed) ──→ leads ┐
    └ the whole pipeline the container assembles with both keys set ──────┘

Everything here is the code the container builds — `build_profile_extractor` does
the wiring, including the cache and the fallback — with two HTTP transports
answering from canned payloads instead of the internet.

Three properties are worth the file:

* reading the page finds things a search result cannot: the bio link that makes one
  person on two platforms **one** lead (§45);
* a page that will not open does not lose the lead, and does not silently pretend
  it was read;
* a page is paid for once (§53), and the search's usage says so (§54).
"""

import httpx
import pytest

from app.api.deps import close_container, open_container
from app.core.config import Settings
from app.core.limits import RateLimiter
from app.models.common import SearchStatus
from app.models.query import LeadQuery
from app.models.search import Search, SearchCriteria
from app.services.adapters import ReaderResources, build_profile_extractor
from app.services.extraction.signal_detector import FixtureSignalDetector
from app.services.scoring.scoring_service import ScoringService
from app.services.scraping.snippet_extractor import MAX_CONFIDENCE as SNIPPET_CONFIDENCE
from app.services.search.pipeline import SearchPipeline
from app.services.search.providers.brave import BraveSearchProvider
from app.services.search.query_generator import TemplateQueryGenerator
from tests.test_live_search import brave_transport, live_criteria

SCRAPE_TOKEN = "sgai-live-token"


def person(**overrides) -> dict:
    base = {
        "is_person": True,
        "name": "Lucía Ferrer",
        "headline": "Líder de equipo · belleza",
        "company": "MIHI Iberia",
        "summary": "Distribuidora independiente y mentora en Valencia.",
        "location": {"country": "Spain", "city": "Valencia"},
        "languages": ["Spanish"],
        "handle": None,
        "followers": None,
        "posts": None,
        "signals": {
            "mlm": {"detected": True, "evidence": "Distribuidora independiente de MIHI"},
            "beauty": {"detected": True, "evidence": "cosmética y cuidado de la piel"},
            "recruiting": {"detected": True, "evidence": "Únete a mi equipo"},
            "leadership": {"detected": True, "evidence": "Líder de equipo desde 2021"},
            "personal_brand": {"detected": False, "evidence": None},
            "activity": {"detected": True, "evidence": "Última publicación hace 2 días"},
        },
        "contacts": {"email": None, "website": None, "phone": None},
        "links": [],
    }
    return {**base, **overrides}


#: One canned page per canonical URL the stubbed Brave returns and the discovery
#: stage accepts. This is the milestone's list: a public profile on each platform, a
#: personal website, and a brand account that is not a person at all.
PAGES: dict[str, dict] = {
    "https://instagram.com/lucia.mihi": person(
        handle="lucia.mihi",
        followers=8420,
        posts=512,
        # The bio link: what a search snippet never carries and a page always might.
        links=["https://www.instagram.com/mihi.oficial/", "https://luciaferrer.es"],
    ),
    "https://es.linkedin.com/in/pablo-serrano-mihi": person(
        name="Pablo Serrano",
        headline="Team Leader — MIHI Iberia",
        location={"country": "Spain", "city": "Valencia"},
        handle="pablo-serrano-mihi",
        contacts={"email": "pablo@example.com", "website": None, "phone": None},
    ),
    "https://facebook.com/rosa.delgado.mlm": person(
        name="Rosa Delgado",
        headline="Distribuidora de cosmética",
        location={"country": "Spain", "city": "Sevilla"},
    ),
    "https://luciaferrer.es/sobre-mi": person(
        summary="Soy Lucía, distribuidora y mentora en el sector de la belleza.",
        contacts={
            "email": "hola@luciaferrer.es",
            "website": "https://luciaferrer.es",
            "phone": None,
        },
    ),
    # The brand's own account: read, and settled as not a person.
    "https://instagram.com/mihi.oficial": {
        "is_person": False,
        "name": "MIHI España",
        "signals": {},
        "contacts": {},
        "links": [],
    },
}

#: The shop and the company page never reach the reader: candidate discovery (§32)
#: rejects them, which is the cheapest possible way not to pay for them.
NEVER_READ = ("tienda-mihi.example.com", "linkedin.com/company")


def page_transport(*, blocked: tuple[str, ...] = (), status: int | None = None):
    """
    Answers like the Extract service: a page per URL. `blocked` makes the named URLs
    behave the way Instagram behaves towards a datacentre IP; `status` makes every
    request fail with that HTTP status.
    """
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = request.read().decode()
        target = next((url for url in PAGES if f'"{url}"' in body), None)
        calls.append(target or body[:80])

        if status is not None:
            return httpx.Response(
                status, json={"error": {"type": "auth_invalid_key", "message": "nope"}}
            )
        if target is None or any(mark in target for mark in blocked):
            # v2 serves the request either way: an unreadable page is an empty
            # extraction plus a fetch diagnostic saying why.
            return httpx.Response(
                200,
                json={
                    "id": "req_blocked",
                    "json": {},
                    "usage": {"promptTokens": 12, "completionTokens": 0},
                    "metadata": {"fetch": {"note": "Login required to view this profile"}},
                },
            )
        return httpx.Response(
            200,
            json={
                "id": "req_ok",
                "json": PAGES[target],
                "usage": {"promptTokens": 420, "completionTokens": 110},
                "metadata": {"fetch": {"status": 200}},
            },
        )

    return calls, handler


def reading_settings(settings: Settings) -> Settings:
    return settings.model_copy(
        update={
            "brave_search_api_key": "brave-token",
            "search_provider": "brave",
            "scrapegraph_api_key": SCRAPE_TOKEN,
        }
    )


async def run_reading(
    settings: Settings, brave_handler, page_handler, *, search_id: str = "srch_read", **criteria
):
    """One search through the pipeline the container builds with both keys set."""
    live = reading_settings(settings)
    container = await open_container(live)
    resources = ReaderResources(
        client=httpx.AsyncClient(transport=httpx.MockTransport(page_handler)),
        limiter=RateLimiter(0),
    )
    try:
        search = Search(
            id=search_id,
            user_id=live.dev_user_id,
            name="Live search that reads pages",
            status=SearchStatus.QUEUED,
            criteria=SearchCriteria.model_validate({**live_criteria(), **criteria}),
        )
        await container.repository.save_search(search)

        extractor = build_profile_extractor(live, [], container.repository, resources)
        pipeline = SearchPipeline(
            repository=container.repository,
            settings=live,
            query_generator=TemplateQueryGenerator(),
            provider=BraveSearchProvider(
                "brave-token",
                client=httpx.AsyncClient(transport=httpx.MockTransport(brave_handler)),
                rate_limit_per_second=0,
            ),
            extractor=extractor,
            detector=FixtureSignalDetector(),
            scoring=ScoringService(),
        )
        await pipeline.run(search.id)

        stored = await container.repository.get_search(search.id)
        page = await container.repository.query_leads(
            live.dev_user_id, LeadQuery(search_id=search.id, page_size=100)
        )
        report = await container.repository.source_reliability()
        return stored, page.items, report
    finally:
        await resources.aclose()
        await close_container(container)


# ------------------------------------------------------------------ the whole run


async def test_the_page_not_the_snippet_is_what_becomes_a_lead(settings):
    _, brave = brave_transport()
    reads, pages = page_transport()

    search, leads, _ = await run_reading(settings, brave, pages)

    assert search is not None and search.status is SearchStatus.COMPLETED
    assert leads, "a live search that reads pages and reports nobody is broken"

    lucia = next(lead for lead in leads if lead.name == "Lucía Ferrer")
    # Evidence in the page's words, quoted from the page — not from the search result.
    quotes = {signal.evidence for signal in lucia.signals if signal.detected}
    assert "Distribuidora independiente de MIHI" in quotes
    assert lucia.headline == "Líder de equipo · belleza"
    assert lucia.company == "MIHI Iberia"
    assert lucia.location and lucia.location.city == "Valencia"
    # Every candidate page was read exactly once, and nothing else was read at all.
    assert sorted(reads) == sorted(PAGES)
    assert not [url for url in reads for mark in NEVER_READ if mark in url]


async def test_a_person_on_two_platforms_is_one_lead_once_the_pages_are_read(settings):
    """
    The gap Phase 4 documented and Phase 5 closes. Lucía is an Instagram profile and
    a personal site; her bio links to the site, so both records carry the same
    website and `deduplicate` merges them on a strong key (spec §45).
    """
    _, brave = brave_transport()
    _, pages = page_transport()

    _, leads, _ = await run_reading(settings, brave, pages)

    lucia = [lead for lead in leads if lead.name == "Lucía Ferrer"]
    assert len(lucia) == 1
    platforms = {entry.platform.value for entry in lucia[0].platforms}
    assert platforms == {"instagram", "website"}
    assert lucia[0].contacts.website == "https://luciaferrer.es"
    # Both pages stay on record as the evidence they are (spec §26).
    assert len(lucia[0].sources) == 2


async def test_a_page_that_says_it_is_not_a_person_is_final(settings):
    """
    The brand account was read, and the snippet gets no second vote — that is how a
    shop comes back as a lead. The shop itself never even reached the reader.
    """
    _, brave = brave_transport()
    reads, pages = page_transport()

    _, leads, report = await run_reading(settings, brave, pages)

    assert not [lead for lead in leads if "MIHI España" in lead.name]
    assert not [lead for lead in leads if "Tienda" in lead.name]
    assert not [url for url in reads if "tienda-mihi" in url]

    by_platform = {row.platform.value: row for row in report}
    assert by_platform["instagram"].pages == 2
    assert by_platform["instagram"].not_a_person == 1
    assert by_platform["instagram"].usable == 1


async def test_the_source_record_is_filled_in_by_a_real_run(settings):
    """Milestone 5's "record which sources provide usable content", after one search."""
    _, brave = brave_transport()
    _, pages = page_transport()

    _, _, report = await run_reading(settings, brave, pages)

    platforms = {row.platform.value for row in report}
    assert platforms >= {"instagram", "linkedin", "facebook", "website"}
    assert all(row.pages > 0 for row in report)
    assert {row.platform.value: row.usable_share for row in report}["linkedin"] == 1.0


# ------------------------------------------------------- pages that will not open


async def test_a_blocked_page_falls_back_to_the_search_result_and_says_so(settings):
    """
    "Do not assume every social-network URL can be scraped." Instagram is blocked
    here, so Lucía's profile comes from the search result instead: still a lead, at
    the confidence a snippet is worth, and the source record says which platform
    refused us.
    """
    _, brave = brave_transport()
    _, pages = page_transport(blocked=("instagram.com",))

    search, leads, report = await run_reading(settings, brave, pages)

    assert search is not None and search.status is SearchStatus.COMPLETED
    # LinkedIn still opened, so this is a source difference, not a broken search.
    assert [lead for lead in leads if lead.name == "Pablo Serrano"]

    by_platform = {row.platform.value: row for row in report}
    assert by_platform["instagram"].blocked == 2
    assert by_platform["instagram"].usable == 0
    assert by_platform["linkedin"].usable == 1

    # And the difference is visible in the evidence: a snippet may never claim as
    # much as a page that was actually read.
    from_snippet = next(
        lead
        for lead in leads
        if any(entry.platform.value == "instagram" for entry in lead.platforms)
    )
    from_page = next(
        lead for lead in leads if any(entry.platform.value == "website" for entry in lead.platforms)
    )
    assert max(signal.confidence for signal in from_snippet.signals) <= SNIPPET_CONFIDENCE
    assert max(signal.confidence for signal in from_page.signals) > SNIPPET_CONFIDENCE


async def test_the_cross_platform_merge_is_what_reading_the_page_bought(settings):
    """
    The other side of the same coin. With Instagram readable, Lucía is one lead
    (her bio link says so); with Instagram blocked, the snippet carries no link and
    she is two — which is exactly the Phase 4 behaviour this phase improved on.

    The cache is off for both runs: two runs against the same database would
    otherwise be one read and one cache hit, and the second transport would never be
    consulted at all. (That the cache does exactly that is what the last test here
    checks.)
    """
    uncached = settings.model_copy(update={"scrape_cache_ttl_hours": 0})
    _, brave = brave_transport()
    _, readable = page_transport()
    _, blocked = page_transport(blocked=("instagram.com",))

    _, merged, _ = await run_reading(uncached, brave, readable, search_id="srch_readable")
    _, split, _ = await run_reading(uncached, brave, blocked, search_id="srch_blocked")

    assert len([lead for lead in merged if lead.name == "Lucía Ferrer"]) == 1
    assert len([lead for lead in split if lead.name == "Lucía Ferrer"]) == 2


async def test_a_rejected_key_does_not_fail_the_search_and_is_not_offered_per_url(settings):
    """
    Extraction is not search: without a reader there is still the search result, so
    the run completes. And a key the provider refused is not offered once per URL for
    the rest of the search (spec §51).

    Concurrency is 1 here on purpose: with the default 10 every URL is already in
    flight before the first refusal comes back, so nothing could be skipped.
    """
    _, brave = brave_transport()
    reads, pages = page_transport(status=401)

    search, leads, report = await run_reading(
        settings.model_copy(update={"extraction_concurrency": 1}), brave, pages
    )

    assert search is not None and search.status is SearchStatus.COMPLETED
    assert leads, "the search results are still there when the reader is not"
    assert len(reads) == 1, "the reader stops after the key is refused"
    assert SCRAPE_TOKEN not in (search.error or "")
    assert sum(row.failed for row in report) >= 1


async def test_an_unreadable_page_is_never_a_person_invented_from_nothing(settings):
    """A reader that answers with nothing must not produce a lead with a name."""
    _, brave = brave_transport()
    _, pages = page_transport(status=500)

    _, leads, _ = await run_reading(settings, brave, pages)

    assert all(lead.name and lead.name != "Unknown" for lead in leads)
    # Whatever survived came from the search results, and each one has its source.
    assert all(lead.sources for lead in leads)


# ----------------------------------------------------------------- what it costs


async def test_pages_are_billed_by_what_was_read(settings):
    _, brave = brave_transport()
    reads, pages = page_transport()

    search, _, _ = await run_reading(settings, brave, pages)

    assert search is not None
    usage = search.usage
    assert usage.pages_read == len(reads) == len(PAGES)
    assert usage.scrape_credits == usage.pages_read
    assert usage.pages_cached == 0
    assert usage.pages_analyzed == search.progress.profiles_processed
    # Search calls plus pages read, at the configured unit prices (spec §54).
    expected = (
        usage.search_api_calls * settings.cost_per_search_call_eur
        + usage.pages_read * settings.cost_per_page_eur
        + usage.llm_calls * settings.cost_per_llm_call_eur
    )
    assert usage.estimated_cost_eur == pytest.approx(round(expected, 2))


async def test_a_second_search_over_the_same_pages_pays_nothing_to_read_them(settings):
    """
    The point of the cache (spec §53): the same twelve queries find the same pages
    tomorrow, and the second run's page bill is zero.
    """
    live = reading_settings(settings)
    _, brave = brave_transport()
    reads, pages = page_transport()

    container = await open_container(live)
    resources = ReaderResources(
        client=httpx.AsyncClient(transport=httpx.MockTransport(pages)), limiter=RateLimiter(0)
    )
    try:
        stored = []
        for index in (1, 2):
            search = Search(
                id=f"srch_twice_{index}",
                user_id=live.dev_user_id,
                name=f"Run {index}",
                status=SearchStatus.QUEUED,
                criteria=SearchCriteria.model_validate(live_criteria()),
            )
            await container.repository.save_search(search)
            pipeline = SearchPipeline(
                repository=container.repository,
                settings=live,
                query_generator=TemplateQueryGenerator(),
                provider=BraveSearchProvider(
                    "brave-token",
                    client=httpx.AsyncClient(transport=httpx.MockTransport(brave)),
                    rate_limit_per_second=0,
                ),
                # A fresh extractor chain per run, exactly as the job service does.
                extractor=build_profile_extractor(live, [], container.repository, resources),
                detector=FixtureSignalDetector(),
                scoring=ScoringService(),
            )
            await pipeline.run(search.id)
            stored.append(await container.repository.get_search(search.id))
    finally:
        await resources.aclose()
        await close_container(container)

    first, second = stored
    assert first is not None and second is not None
    assert first.usage.pages_read == len(PAGES)
    assert second.usage.pages_read == 0
    assert second.usage.pages_cached == second.usage.pages_analyzed
    assert second.usage.estimated_cost_eur < first.usage.estimated_cost_eur
    # And the pages themselves were fetched once in total.
    assert len(reads) == len(PAGES)
    # The second run still produced the same people.
    assert second.lead_count == first.lead_count
