"""
Criteria → real URLs → stored leads (spec §60, Milestone 4).

The pipeline is assembled exactly as the container assembles it with a Brave key
configured — live provider, snippet extractor, real database — with one difference:
Brave's HTTP transport answers from the canned payload below instead of the
internet. So this exercises the whole path, including the parts that only exist
when the URLs are ones the seeded catalogue has never heard of.
"""

import httpx
import pytest

from app.api.deps import close_container, open_container
from app.core.config import Settings
from app.models.common import SearchStatus
from app.models.query import LeadQuery
from app.models.search import Search, SearchCriteria
from app.services.extraction.signal_detector import FixtureSignalDetector
from app.services.scoring.scoring_service import ScoringService
from app.services.scraping.snippet_extractor import SnippetProfileExtractor
from app.services.search.pipeline import SearchPipeline
from app.services.search.providers.brave import BraveSearchProvider
from app.services.search.query_generator import TemplateQueryGenerator
from tests.conftest import MIHI_SPAIN, start_search, wait_for, wait_for_job

#: Results in Brave's shape, keyed by the site: operator the query carries. Nobody
#: in the seeded catalogue appears here — that is the point.
WEB: dict[str, list[dict]] = {
    "instagram.com": [
        {
            "title": "Lucía Ferrer (@lucia.mihi) • Instagram photos and videos",
            "url": "https://www.instagram.com/lucia.mihi/?utm_source=brave",
            "description": (
                "8,420 Followers, 512 Posts — Lucía Ferrer (@lucia.mihi): network marketing "
                "y belleza en España. Líder de equipo, únete a mi equipo."
            ),
            "language": "es",
            "age": "2 days ago",
        },
        {
            "title": "MIHI España (@mihi.oficial) • Instagram",
            "url": "https://www.instagram.com/mihi.oficial/",
            "description": "Official brand account. 44,000 Followers.",
        },
    ],
    "linkedin.com": [
        {
            "title": "Pablo Serrano - Team Leader - MIHI Iberia | LinkedIn",
            "url": "https://es.linkedin.com/in/pablo-serrano-mihi",
            "description": (
                "Distribuidor independiente y mentor de equipo. Cosmética, "
                "network marketing. Valencia, España."
            ),
            "language": "es",
        },
        {
            "title": "MIHI Iberia | LinkedIn",
            "url": "https://www.linkedin.com/company/mihi-iberia",
            "description": "Company page",
        },
    ],
    "facebook.com": [
        {
            "title": "Rosa Delgado | Facebook",
            "url": "https://www.facebook.com/rosa.delgado.mlm",
            "description": "Distribuidora de cosmética en Sevilla, España. Buscamos colaboradores.",
            "language": "es",
        }
    ],
    "": [
        {
            "title": "Lucía Ferrer — coach de network marketing en España",
            "url": "https://luciaferrer.es/sobre-mi",
            "description": "Soy Lucía, distribuidora y mentora en el sector de la belleza.",
            "language": "es",
            "page_age": "2026-08-10T09:00:00Z",
        },
        {
            "title": "Comprar cosmética MIHI online | Tienda oficial",
            "url": "https://tienda-mihi.example.com/shop",
            "description": "Envío gratis en pedidos superiores a 50 €.",
        },
    ],
}


def brave_transport(*, fails: str | None = None, status: int = 500):
    """
    Answers like Brave does: results chosen by the query's `site:` operator. `fails`
    makes every query mentioning that string return `status` instead.
    """
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        query = request.url.params.get("q", "")
        calls.append(query)
        if fails is not None and fails in query:
            return httpx.Response(status, json={"error": "nope"})
        site = next((key for key in WEB if key and f"site:{key}" in query), "")
        return httpx.Response(200, json={"web": {"results": WEB[site]}})

    return calls, handler


def pipeline_for(settings: Settings, handler, repository) -> SearchPipeline:
    return SearchPipeline(
        repository=repository,
        settings=settings,
        query_generator=TemplateQueryGenerator(),
        provider=BraveSearchProvider(
            "test-token",
            client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
            rate_limit_per_second=0,
        ),
        extractor=SnippetProfileExtractor(),
        detector=FixtureSignalDetector(),
        scoring=ScoringService(),
    )


async def run_live(settings: Settings, handler, **criteria: object):
    """Runs one search through the live-search pipeline and returns what was stored."""
    container = await open_container(settings)
    try:
        search = Search(
            id="srch_live",
            user_id=settings.dev_user_id,
            name="Live web search",
            status=SearchStatus.QUEUED,
            criteria=SearchCriteria.model_validate({**_criteria(), **criteria}),
        )
        await container.repository.save_search(search)

        await pipeline_for(settings, handler, container.repository).run(search.id)

        stored = await container.repository.get_search(search.id)
        page = await container.repository.query_leads(
            settings.dev_user_id, LeadQuery(search_id=search.id, page_size=100)
        )
        return stored, page.items
    finally:
        await close_container(container)


def _criteria() -> dict:
    """The wizard's example scenario, in snake_case as the domain model wants it."""
    return {
        "industry": MIHI_SPAIN["industry"],
        "business_types": MIHI_SPAIN["businessTypes"],
        "keywords": MIHI_SPAIN["keywords"],
        "negative_keywords": MIHI_SPAIN["negativeKeywords"],
        "location": MIHI_SPAIN["location"],
        "languages": MIHI_SPAIN["languages"],
        "must_have": ["mlm", "beauty"],
        "nice_to_have": MIHI_SPAIN["niceToHave"],
        "signal_weights": MIHI_SPAIN["signalWeights"],
        "sources": MIHI_SPAIN["sources"],
    }


# --------------------------------------------------------------------- the run


async def test_a_live_search_stores_leads_found_on_the_open_web(settings):
    calls, handler = brave_transport()

    search, leads = await run_live(settings, handler)

    assert search is not None and search.status is SearchStatus.COMPLETED
    assert leads, "a live search that finds nobody is a broken search"

    # Every lead points at a URL the provider returned, normalized (spec §31).
    found = {entry.url for lead in leads for entry in lead.platforms}
    assert "https://instagram.com/lucia.mihi" in found or found & {
        "https://www.instagram.com/lucia.mihi/?utm_source=brave"
    }
    assert {lead.name for lead in leads} >= {"Lucía Ferrer", "Pablo Serrano", "Rosa Delgado"}
    # The catalogue is unreachable in live mode: none of the seeded people appear.
    assert all(lead.search_id == search.id for lead in leads)


async def test_the_brand_account_and_the_shop_are_not_people(settings):
    """§32 and the extractor's own bar, over data that mixes both in."""
    _, handler = brave_transport()

    _, leads = await run_live(settings, handler)

    assert not [lead for lead in leads if "MIHI España" in lead.name]
    assert not [lead for lead in leads if "Comprar" in lead.name]


async def test_the_same_url_found_by_several_queries_is_one_lead(settings):
    """
    Every `site:instagram.com` query returns Lucía's profile, one of them with
    tracking parameters attached. Milestone 4's URL deduplication is what makes
    that one candidate, one extraction and one lead (spec §31).
    """
    calls, handler = brave_transport()

    search, leads = await run_live(settings, handler)

    assert search is not None
    instagram = [
        lead
        for lead in leads
        if any(
            entry.url.startswith("https://www.instagram.com/lucia.mihi") for entry in lead.platforms
        )
    ]
    assert len(instagram) == 1
    # Many raw results, far fewer unique URLs, fewer still worth extracting.
    assert search.progress.urls_discovered > search.progress.profiles_discovered
    assert search.progress.profiles_processed == search.progress.profiles_discovered


async def test_a_person_on_two_platforms_needs_a_page_to_be_recognised_as_one(settings):
    """
    Lucía is both an Instagram profile and her own domain, and the two stay two
    leads: `deduplicate` merges on strong keys only — a shared URL, handle, e-mail
    or website — and a search snippet carries none of the links that would connect
    them (spec §45). Phase 5 reads the pages, where the bio link and the site's
    social icons make the same two records overlap.
    """
    _, handler = brave_transport()

    _, leads = await run_live(settings, handler)

    lucia = [lead for lead in leads if lead.name == "Lucía Ferrer"]
    assert len(lucia) == 2
    assert {lead.platforms[0].platform.value for lead in lucia} == {"instagram", "website"}


async def test_every_query_is_one_billed_call_and_the_cost_is_reported(settings):
    calls, handler = brave_transport()

    search, _ = await run_live(settings, handler)

    assert search is not None
    assert search.usage.search_api_calls == len(calls) == search.progress.queries
    assert search.usage.estimated_cost_eur > 0
    assert all(entry.provider == "brave" for entry in search.queries)


async def test_the_country_reaches_the_provider_as_a_market(settings):
    calls, handler = brave_transport()
    seen: list[httpx.Request] = []

    def recording(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return handler(request)

    await run_live(settings, recording)

    assert seen and all(request.url.params["country"] == "ES" for request in seen)


# ---------------------------------------------------------------- when it fails


async def test_a_query_that_fails_does_not_lose_the_ones_that_worked(settings):
    """Spec §51: eleven good queries beat an error page."""
    calls, handler = brave_transport(fails="facebook", status=503)

    search, leads = await run_live(settings, handler)

    assert search is not None and search.status is SearchStatus.COMPLETED
    assert leads
    assert search.usage.search_api_calls < search.progress.queries
    assert not [lead for lead in leads if lead.name == "Rosa Delgado"]


async def test_a_search_where_nothing_answered_fails_loudly(settings):
    _, handler = brave_transport(fails="", status=503)

    search, leads = await run_live(settings, handler)

    assert search is not None and search.status is SearchStatus.FAILED
    assert search.error and "Brave" in search.error
    assert leads == []


async def test_a_rejected_key_says_what_to_fix_and_never_quotes_itself(settings):
    _, handler = brave_transport(fails="", status=401)

    search, _ = await run_live(settings, handler)

    assert search is not None and search.status is SearchStatus.FAILED
    assert "BRAVE_SEARCH_API_KEY" in (search.error or "")
    assert "test-token" not in (search.error or "")


def test_a_failed_search_is_a_failed_job_in_the_operator_view(client, settings):
    """
    The pipeline handles provider errors itself and returns cleanly, so nothing
    raises — the job record has to read the search's outcome or `/jobs` would call
    a search that produced an error message a success (spec §40).
    """
    container = client.app.state.container
    _, handler = brave_transport(fails="", status=401)
    container.jobs._pipeline_factory = lambda: pipeline_for(settings, handler, container.repository)

    search_id = start_search(client, name="Live search with a bad key")

    assert wait_for(client, search_id)["status"] == "failed"
    job = wait_for_job(client, search_id)
    assert job["status"] == "failed"
    assert "BRAVE_SEARCH_API_KEY" in job["error"]


async def test_a_rejected_key_costs_one_call_per_query_not_three(settings):
    calls, handler = brave_transport(fails="", status=401)

    search, _ = await run_live(settings, handler)

    assert search is not None
    assert len(calls) == search.progress.queries


# --------------------------------------------------------- two of the same name


async def test_two_different_people_with_the_same_name_stay_two_leads(settings):
    """
    On the open web a name is not an identity. Before Phase 4 the lead id was the
    name, so this pair would have overwritten each other in the database.
    """
    same_name = [
        {
            "title": "María García (@maria.garcia.mihi) • Instagram photos",
            "url": "https://www.instagram.com/maria.garcia.mihi/",
            "description": "Network marketing, belleza. Madrid, España. 5,000 Followers",
            "language": "es",
        },
        {
            "title": "María García (@mgarcia.beauty) • Instagram photos",
            "url": "https://www.instagram.com/mgarcia.beauty/",
            "description": "Distribuidora de cosmética en Bilbao, España. 3,100 Followers",
            "language": "es",
        },
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"web": {"results": same_name}})

    _, leads = await run_live(settings, handler)

    garcias = [lead for lead in leads if lead.name == "María García"]
    assert len(garcias) == 2
    assert len({lead.id for lead in garcias}) == 2


@pytest.mark.parametrize("must_have", [["mlm", "beauty"], ["mlm", "beauty", "location"]])
async def test_must_have_criteria_still_gate_live_results(settings, must_have):
    """Whatever the source, "required" means required (spec §37)."""
    _, handler = brave_transport()

    _, leads = await run_live(settings, handler, must_have=must_have)

    assert leads
    for lead in leads:
        assert set(must_have) <= {signal.type.value for signal in lead.signals if signal.detected}
