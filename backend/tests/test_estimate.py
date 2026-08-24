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
    assert priced.credits == 15 * settings.scrapegraph_credits_per_page


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
