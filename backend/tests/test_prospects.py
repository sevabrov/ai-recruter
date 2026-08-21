"""
Which candidate is worth a credit (spec §52).

Once the number of pages a search may read is limited, the order they are read in
becomes the decision that limit hangs on — and before this it was made by whichever
coroutine `asyncio.gather` started first. A hundred candidates, twenty-five paid
reads, and the twenty-five were arbitrary.

Ranking is free: it uses the search result the provider already returned. What is
worth testing is that it orders by evidence, that a source which actually opens is
preferred at equal evidence, and — the property that keeps this honest — that
nothing is ever dropped. A snippet is not allowed to disqualify a page; only the
page can do that.
"""

import pytest

from app.models.common import Platform, SignalType
from app.models.search import SearchCriteria
from app.models.source import DiscoveredUrl, UrlKind
from app.services.scoring.scoring_service import ScoringService
from app.services.scraping.snippet_extractor import SnippetProfileExtractor
from app.services.search.prospects import PLATFORM_PRIOR, rank

pytestmark = pytest.mark.anyio

CRITERIA = SearchCriteria.model_validate(
    {
        "keywords": ["MIHI", "beauty", "network marketing"],
        "industry": ["Beauty"],
        "businessTypes": ["MLM"],
        "location": {"country": "Spain"},
        "languages": ["Spanish"],
        "mustHave": [SignalType.MLM.value],
        "niceToHave": [SignalType.LEADERSHIP.value],
        "sources": ["instagram_public", "linkedin_public"],
    }
)


def candidate(
    handle: str,
    *,
    platform: Platform = Platform.INSTAGRAM,
    title: str | None = None,
    snippet: str = "",
) -> DiscoveredUrl:
    host = {
        Platform.INSTAGRAM: "instagram.com",
        Platform.LINKEDIN: "es.linkedin.com/in",
        Platform.WEBSITE: "example.es",
    }[platform]
    return DiscoveredUrl(
        url=f"https://{host}/{handle}",
        canonical_url=f"https://{host}/{handle}",
        platform=platform,
        kind=UrlKind.CANDIDATE,
        title=title if title is not None else f"Marta Ruiz (@{handle}) • Instagram",
        snippet=snippet,
        query="site:instagram.com MIHI Spain",
        provider="brave",
        language="es",
    )


async def ranked(urls: list[DiscoveredUrl]):
    return await rank(
        urls,
        CRITERIA,
        snippets=SnippetProfileExtractor(),
        scoring=ScoringService(),
    )


async def test_the_candidate_whose_result_already_shows_the_signals_goes_first():
    thin = candidate("marta.thin", snippet="Fotos y vídeos")
    strong = candidate(
        "marta.strong",
        snippet=(
            "Distribuidora independiente MIHI · líder de equipo de belleza en Valencia, "
            "España. Únete a mi equipo. 12.4K followers"
        ),
    )

    order = await ranked([thin, strong])

    assert [prospect.url.canonical_url for prospect in order] == [
        strong.canonical_url,
        thin.canonical_url,
    ]
    assert order[0].promise > order[1].promise


async def test_a_must_have_signal_in_the_snippet_counts_extra():
    """
    The gate is `must_have`, so a page that already shows one is likelier to survive
    it than a page that has to prove everything from scratch.
    """
    mlm = candidate("marta.mlm", snippet="Distribuidora independiente MIHI")
    other = candidate("marta.other", snippet="Líder de equipo desde 2021")

    order = await ranked([mlm, other])

    assert order[0].url.canonical_url == mlm.canonical_url


async def test_at_equal_evidence_the_source_that_opens_is_read_first():
    """
    Promise means "worth paying to read", and half of that is whether the page will
    open at all. Milestone 5's own record says a personal site does and an Instagram
    profile shows a login wall to a server.
    """
    evidence = "Distribuidora independiente MIHI, belleza, España"
    social = candidate("marta.ig", snippet=evidence)
    site = candidate(
        "sobre-mi",
        platform=Platform.WEBSITE,
        title="Marta Ruiz — distribuidora de belleza",
        snippet=evidence,
    )

    order = await ranked([social, site])

    assert order[0].url.platform is Platform.WEBSITE
    assert PLATFORM_PRIOR[Platform.WEBSITE] > PLATFORM_PRIOR[Platform.INSTAGRAM]


async def test_a_candidate_the_snippet_cannot_name_keeps_its_place_in_the_queue():
    """
    A personal site rarely announces a person in its title, and dropping it would
    lose exactly the leads reading pages is for. It ranks low, not out.
    """
    nameless = candidate(
        "equipo",
        platform=Platform.WEBSITE,
        title="Bienvenida a nuestra web",
        snippet="Cosmética natural",
    )
    named = candidate("marta.named", snippet="Distribuidora MIHI")

    order = await ranked([nameless, named])

    assert len(order) == 2
    assert order[-1].url.canonical_url == nameless.canonical_url
    assert order[-1].profile is None, "the snippet found no person — the page may still"


async def test_ranking_drops_nothing_and_reads_nothing():
    urls = [candidate(f"person{index}", snippet="belleza") for index in range(6)]

    order = await ranked(urls)

    assert len(order) == len(urls)
    assert {prospect.url.canonical_url for prospect in order} == {url.canonical_url for url in urls}


async def test_ties_keep_discovery_order_so_a_search_is_reproducible():
    urls = [candidate(f"same{index}", snippet="belleza") for index in range(4)]

    first = await ranked(urls)
    again = await ranked(urls)

    assert [prospect.promise for prospect in first] == [prospect.promise for prospect in again]
    assert [prospect.url.canonical_url for prospect in first] == [
        prospect.url.canonical_url for prospect in again
    ]
