"""
"How many leads do I want, and what will that cost?" (spec §54)

The client asked for both to be answered in the wizard, before the search starts,
and the second one is only worth showing if it is true. So the number is a
**ceiling, not a forecast**, and the property this file exists to hold is that
the ceiling is the same object as the limit: `page_budget_for` produces the
figure the wizard quotes *and* the budget the run is given, so a search cannot
cost more than it was quoted for.

The rest is arithmetic, and the tests are here to keep it legible: asking for
more leads buys more pages, the server's own ceiling still wins, and a stage that
is not plugged in is not billed for.
"""

import pytest

from app.core.config import Settings
from app.models.search import SearchCriteria
from app.services.search.estimate import estimate, page_budget_for
from app.services.search.query_generator import TemplateQueryGenerator

pytestmark = pytest.mark.anyio


def criteria(**overrides) -> SearchCriteria:
    return SearchCriteria.model_validate(
        {
            "keywords": ["network marketing"],
            "industry": ["beauty"],
            "location": {"country": "Spain"},
            "languages": ["Spanish"],
            "sources": ["instagram_public", "linkedin_public"],
            **overrides,
        }
    )


def quote(settings: Settings, **overrides):
    return estimate(
        criteria(**overrides),
        settings,
        generator=TemplateQueryGenerator(),
        reads_pages=True,
    )


# ------------------------------------------------------------------- the budget


def test_the_leads_asked_for_are_what_buys_the_pages(settings):
    settings = settings.model_copy(update={"pages_per_lead": 3, "max_pages_per_search": 25})

    assert page_budget_for(criteria(target_leads=5), settings) == 15
    assert page_budget_for(criteria(target_leads=2), settings) == 6


def test_the_server_ceiling_still_wins(settings):
    """The wizard is a control, not an override: nobody types their way past §52."""
    settings = settings.model_copy(update={"pages_per_lead": 3, "max_pages_per_search": 25})

    assert page_budget_for(criteria(target_leads=100), settings) == 25


def test_no_target_means_the_server_default(settings):
    settings = settings.model_copy(update={"max_pages_per_search": 25, "target_leads": 0})

    assert page_budget_for(criteria(), settings) == 25


def test_a_ceiling_of_zero_is_unlimited_and_says_so(settings):
    settings = settings.model_copy(update={"max_pages_per_search": 0, "target_leads": 0})

    assert page_budget_for(criteria(), settings) == 0
    assert quote(settings).unlimited_pages


# -------------------------------------------------------------------- the price


def test_the_price_is_the_calls_plus_the_pages(settings):
    settings = settings.model_copy(
        update={
            "pages_per_lead": 3,
            "max_pages_per_search": 25,
            "cost_per_search_call_eur": 0.005,
            "cost_per_page_eur": 0.010,
            "openai_api_key": "",
        }
    )

    priced = quote(settings, target_leads=5)

    assert priced.max_pages == 15
    assert priced.max_cost_eur == pytest.approx(priced.search_calls * 0.005 + 15 * 0.010)
    # Credits quote what the pages will actually be charged: the extraction plus the
    # residential proxy, since the social platforms are read through it.
    per_page = settings.scrapegraph_credits_per_page + settings.scrapegraph_stealth_credits
    assert priced.credits == 15 * per_page


def test_a_stage_that_is_not_plugged_in_is_not_priced(settings):
    """No page-reader key: the search reads search results, and pages cost nothing."""
    priced = estimate(
        criteria(target_leads=5),
        settings,
        generator=TemplateQueryGenerator(),
        reads_pages=False,
    )

    assert (priced.max_pages, priced.credits) == (0, 0)
    calls = priced.search_calls * settings.cost_per_search_call_eur
    assert priced.max_cost_eur == pytest.approx(calls)


def test_pages_our_browser_reads_are_not_priced(settings):
    """An Instagram-only search was quoted 25 paid pages and paid for none."""
    from app.services.scraping.browser_reader import BROWSER_SOURCES

    settings = settings.model_copy(update={"cost_per_page_eur": 0.010})

    def priced(sources: list[str]):
        return estimate(
            criteria(target_leads=10, sources=sources),
            settings,
            generator=TemplateQueryGenerator(),
            reads_pages=True,
            free_sources=BROWSER_SOURCES,
        )

    social = priced(["instagram_public", "facebook_public"])
    mixed = priced(["instagram_public", "linkedin_public"])

    assert (social.reads_pages, social.max_pages, social.credits) == (False, 0, 0)
    assert social.browser_pages
    assert social.max_cost_eur == pytest.approx(
        social.search_calls * settings.cost_per_search_call_eur
    )
    # LinkedIn still goes to the paid reader, so a mixed search still buys pages.
    assert mixed.reads_pages and mixed.max_pages > 0 and mixed.browser_pages


def test_the_expected_price_is_the_usual_judging_never_above_the_ceiling(settings):
    """Fourteen runs judged 1.5–3.8 candidates per lead; the ceiling assumes 10."""
    settings = settings.model_copy(
        update={
            "openai_api_key": "sk-test",
            "cost_per_llm_call_eur": 0.004,
            "judgements_per_lead": 10,
            "expected_judgements_per_lead": 4,
        }
    )
    priced = estimate(
        criteria(target_leads=25),
        settings,
        generator=TemplateQueryGenerator(),
        reads_pages=True,
        paid_detector=True,
    )

    judging_ceiling = 250 * 0.004
    judging_usual = 100 * 0.004
    assert priced.max_cost_eur - priced.expected_cost_eur == pytest.approx(
        judging_ceiling - judging_usual, abs=0.011
    )
    assert priced.expected_cost_eur <= priced.max_cost_eur


def test_asking_in_more_languages_costs_more_calls_and_the_quote_shows_it(settings):
    one = quote(settings, languages=["Spanish"])
    three = quote(settings, languages=["Spanish", "Russian", "Ukrainian"])

    assert three.search_calls > one.search_calls
    assert three.max_cost_eur > one.max_cost_eur


def test_the_quote_lists_the_queries_the_search_will_actually_run(settings):
    """
    Not a re-implementation of them. The browser had its own copy of the templates
    and the two drifted the moment the backend learned to translate.
    """
    priced = quote(settings)
    generated = TemplateQueryGenerator().generate(criteria(), limit=settings.max_queries_per_search)

    assert [plan.query for plan in priced.queries] == [plan.query for plan in generated]


def test_the_quote_warns_about_criteria_that_will_return_nothing(settings):
    """
    The complaint was never that the filters were wrong — it was that a
    reasonable-looking set of them returned nothing, and the screen blamed the
    filters afterwards. Saying it first costs nothing.
    """
    strict = quote(
        settings,
        sources=["instagram_public"],
        require_confirmed_location=True,
        must_have=["mlm", "beauty", "activity"],
    )

    codes = {note.code for note in strict.warnings}
    assert "confirmed_location_social" in codes
    assert "many_must_have" in codes
    assert "activity_must_have" in codes
    # And a workable set of criteria is not nagged at.
    assert quote(settings, must_have=["mlm"]).warnings == []


def test_warnings_are_codes_not_english_sentences(settings):
    """
    The wording is the interface's: an English sentence in the middle of a
    Ukrainian screen was the first thing the client asked to have removed.
    """
    bare = quote(settings, keywords=[], brands=[])
    no_keywords = next(note for note in bare.warnings if note.code == "no_keywords")
    assert no_keywords.params == {}

    # A brand is a term of the client's own, so it silences the warning.
    branded = quote(settings, keywords=[], brands=["Farmasi"])
    assert "no_keywords" not in {note.code for note in branded.warnings}


def test_languages_without_a_country_are_flagged(settings):
    """Without a place to write in Ukrainian, no Ukrainian query is written at all."""
    loose = quote(settings, languages=["Ukrainian", "Russian"], location={"country": None})
    assert "languages_without_country" in {note.code for note in loose.warnings}

    anchored = quote(settings, languages=["Ukrainian"], location={"country": "Ukraine"})
    assert "languages_without_country" not in {note.code for note in anchored.warnings}


# --------------------------------------------------------------- over the wire


def test_the_wizard_can_price_a_search_without_creating_one(client):
    before = client.get("/searches").json()

    response = client.post(
        "/searches/estimate",
        json={
            "criteria": {
                "keywords": ["network marketing"],
                "industry": ["Beauty"],
                "location": {"country": "Ukraine"},
                "languages": ["Ukrainian", "Russian"],
                "sources": ["instagram_public", "linkedin_public"],
                "targetLeads": 10,
            }
        },
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["targetLeads"] == 10
    assert body["searchCalls"] == len(body["queries"])
    assert body["maxCostEur"] >= 0
    assert any(entry["language"] == "uk" for entry in body["queries"])
    assert client.get("/searches").json() == before, "estimating must not create anything"


def test_the_search_is_created_with_the_target_the_client_chose(client):
    response = client.post(
        "/searches",
        json={
            "name": "Ten leads please",
            "criteria": {
                "keywords": ["network marketing"],
                "location": {"country": "Spain"},
                "sources": ["instagram_public"],
                "targetLeads": 10,
                "requireLocation": False,
            },
        },
    )

    assert response.status_code == 202, response.text
    search = client.get(f"/searches/{response.json()['searchId']}").json()
    assert search["criteria"]["targetLeads"] == 10
    assert search["criteria"]["requireLocation"] is False
    assert search["criteria"]["requireLanguage"] is True
