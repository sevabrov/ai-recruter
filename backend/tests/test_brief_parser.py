"""
Reading the client's free-text brief into criteria.

No test reaches OpenAI: the parser takes its HTTP client, so the transport is a
canned Chat Completions answer. What is worth testing is what we do with that
answer — what is kept, what is refused, and what happens when there is none.
"""

import json

import httpx

from app.models.common import SignalType, SourceKind
from app.models.search import SearchCriteria
from app.services.brief.parser import (
    DEFAULT_SOURCES,
    OpenAIBriefParser,
    ResilientBriefParser,
    RuleBriefParser,
    build_criteria,
)
from app.services.search.query_generator import TemplateQueryGenerator

BRIEF = (
    "Я лідерка MIHI в Іспанії. Шукаю жінок, які вже працюють у мережевому маркетингу "
    "в косметиці — Фармасі, Джерелія — і мають свою команду. Україно- та "
    "російськомовні, Іспанія. Не магазини і не салони. Потрібно 25 лідів."
)

#: What a well-behaved model returns for BRIEF.
MODEL_ANSWER = {
    "name": "Лідерки косметики в Іспанії",
    "about_me": "Лідерка MIHI в Іспанії",
    "brands": ["Farmasi", "Фармасі", "Jerelia", "Джерелія"],
    "keywords": ["мережевий маркетинг", "лідер команди"],
    "negative_keywords": ["магазин", "салон"],
    "industries": ["Cosmetics"],
    "business_types": ["Network marketing"],
    "country": "ES",
    "city": "",
    "languages": ["uk", "ru", "es"],
    "must_have": ["mlm"],
    "nice_to_have": ["beauty", "leadership"],
    "sources": [],
    "target_leads": 25,
}


def model_parser(answer: dict | None = None, status: int = 200, seen: list | None = None):
    def handler(request: httpx.Request) -> httpx.Response:
        if seen is not None:
            seen.append(request)
        if status != 200:
            return httpx.Response(status, json={"error": {"message": "nope"}})
        body = {"choices": [{"message": {"content": json.dumps(answer or MODEL_ANSWER)}}]}
        return httpx.Response(200, json=body)

    return OpenAIBriefParser(
        "sk-test",
        model="test-model",
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )


# ------------------------------------------------------------------- the model


async def test_the_model_answer_becomes_criteria_in_the_clients_own_words():
    parsed = await model_parser().parse(BRIEF, "uk")

    criteria = parsed.criteria
    assert parsed.parser == "openai"
    assert parsed.name == "Лідерки косметики в Іспанії"
    # Search terms stay as written — Cyrillic and all.
    assert criteria.brands == ["Farmasi", "Фармасі", "Jerelia", "Джерелія"]
    assert criteria.keywords == ["мережевий маркетинг", "лідер команди"]
    # Closed vocabularies become the tokens the backend keys on.
    assert criteria.location.country == "Spain"
    assert criteria.languages == ["Ukrainian", "Russian", "Spanish"]
    assert criteria.target_leads == 25
    # The client's own brand is context, not a search term.
    assert "MIHI" not in criteria.brands
    assert criteria.about_me == "Лідерка MIHI в Іспанії"
    # And what they typed is kept, so a re-run starts from it.
    assert criteria.brief == BRIEF


async def test_the_request_asks_for_a_strict_schema_and_sends_the_key():
    seen: list[httpx.Request] = []
    await model_parser(seen=seen).parse(BRIEF, "uk")

    request = seen[0]
    assert request.headers["authorization"] == "Bearer sk-test"
    body = json.loads(request.content)
    assert body["model"] == "test-model"
    schema = body["response_format"]["json_schema"]
    assert schema["strict"] is True
    assert set(schema["schema"]["required"]) == set(schema["schema"]["properties"])
    assert body["messages"][-1]["content"] == BRIEF


async def test_a_failing_model_falls_back_to_the_rules_instead_of_an_error():
    parser = ResilientBriefParser(model_parser(status=401))

    parsed = await parser.parse(BRIEF, "uk")

    assert parsed.parser == "rules"
    assert parsed.criteria.location.country == "Spain"


# --------------------------------------------------------------- normalising


def test_values_outside_the_closed_lists_are_dropped_not_guessed():
    criteria = build_criteria(
        {
            "country": "ZZ",
            "languages": ["uk", "xx", "en-GB"],
            "industries": ["Cosmetics", "Rocketry"],
            "must_have": ["mlm", "telepathy"],
            "sources": ["instagram_public", "myspace"],
            "keywords": ["консультант", "a whole sentence that nobody writes in a bio ever"],
            "target_leads": 5000,
        },
        "brief",
    )

    assert criteria.location.country is None
    assert criteria.languages == ["Ukrainian", "English"]
    assert criteria.industry == ["Cosmetics"]
    assert criteria.must_have == [SignalType.MLM]
    assert criteria.sources == [SourceKind.INSTAGRAM_PUBLIC]
    assert criteria.keywords == ["консультант"]
    assert criteria.target_leads == 1000


def test_a_cyrillic_brand_also_gets_its_latin_name():
    """`фармасі` and `farmasi` are two queries reaching two sets of people."""
    criteria = build_criteria({"brands": ["Фармасі", "MyLocalBrand"]}, "brief")

    assert criteria.brands == ["Фармасі", "Farmasi", "MyLocalBrand"]


def test_requirements_are_taken_as_the_brief_states_them():
    """No signal is promoted, demoted or added: the brief decides what is required."""
    criteria = build_criteria(
        {"must_have": ["leadership", "recruiting"], "nice_to_have": ["recruiting", "beauty"]},
        "brief",
    )

    assert criteria.must_have == [SignalType.LEADERSHIP, SignalType.RECRUITING]
    # A signal is required or preferred, never both.
    assert criteria.nice_to_have == [SignalType.BEAUTY]


def test_nothing_about_network_marketing_is_assumed():
    """The product recruits for any role; a search for developers needs no MLM gate."""
    criteria = build_criteria({}, "brief")

    assert criteria.must_have == []
    assert criteria.nice_to_have == []
    assert criteria.business_types == []
    assert criteria.sources == list(DEFAULT_SOURCES)
    assert SourceKind.PUBLIC_WEB not in criteria.sources
    # Missing is missing — nothing is invented for the review screen to un-invent.
    assert criteria.brands == []
    assert criteria.keywords == []
    assert criteria.location.country is None


# -------------------------------------------------------------------- the rules


async def test_the_rules_read_countries_languages_brands_and_a_count():
    parsed = await RuleBriefParser().parse(BRIEF, "uk")
    criteria = parsed.criteria

    assert parsed.parser == "rules"
    assert criteria.location.country == "Spain"
    assert {"Ukrainian", "Russian"} <= set(criteria.languages)
    assert "фармасі" in criteria.brands and "Farmasi" in criteria.brands
    assert "джерелія" in criteria.brands and "Jerelia" in criteria.brands
    assert criteria.target_leads == 25


async def test_a_language_is_not_mistaken_for_a_country():
    """'українською' names a language; it must not send the search to Ukraine."""
    parsed = await RuleBriefParser().parse("Шукаю консультантів, які пишуть українською.", "uk")

    assert parsed.criteria.location.country is None
    assert parsed.criteria.languages == ["Ukrainian"]


# ------------------------------------------------------------ into the queries


def test_each_brand_is_asked_on_every_chosen_platform_first():
    criteria = SearchCriteria(
        brands=["джерелія"],
        keywords=["консультант"],
        sources=[SourceKind.INSTAGRAM_PUBLIC, SourceKind.FACEBOOK_PUBLIC],
    )

    queries = [plan.query for plan in TemplateQueryGenerator().generate(criteria, limit=24)]

    assert queries[:2] == ["site:instagram.com джерелія", "site:facebook.com джерелія"]


def test_a_search_for_any_other_role_gets_no_network_marketing_words():
    """No "distributor", no "team leader", no fallback to "network marketing"."""
    criteria = SearchCriteria(
        keywords=["Python developer", "Django"],
        industry=[],
        location={"country": "Poland"},
        languages=["Polish"],
        sources=[SourceKind.LINKEDIN_PUBLIC, SourceKind.PUBLIC_WEB],
    )

    queries = [plan.query for plan in TemplateQueryGenerator().generate(criteria, limit=24)]

    # Polish was asked for, so the place is written the way Poles write it.
    assert 'site:linkedin.com/in "Python developer" Polska' in queries
    assert 'site:linkedin.com/in "Django" Polska' in queries
    lowered = " ".join(queries).casefold()
    for niche_word in ("distributor", "team leader", "network marketing", "beauty", "дистриб"):
        assert niche_word not in lowered


def test_a_network_marketing_search_keeps_its_templates():
    criteria = SearchCriteria(
        keywords=["консультант"],
        business_types=["MLM"],
        location={"country": "Spain"},
        sources=[SourceKind.INSTAGRAM_PUBLIC],
    )

    queries = [plan.query for plan in TemplateQueryGenerator().generate(criteria, limit=24)]

    assert any("distributor" in query for query in queries)


def test_brands_alone_carry_a_search_for_any_role():
    """No words of the client's own: nothing generic is invented around the brand."""
    criteria = SearchCriteria(brands=["SoftServe"], sources=[SourceKind.LINKEDIN_PUBLIC])

    queries = [plan.query for plan in TemplateQueryGenerator().generate(criteria, limit=24)]

    assert queries == ["site:linkedin.com/in SoftServe"]


# --------------------------------------------------------------- over the wire


def test_the_parse_endpoint_answers_without_a_model(client):
    response = client.post("/searches/parse", json={"text": BRIEF, "locale": "uk"})

    assert response.status_code == 200
    body = response.json()
    assert body["parser"] == "rules"
    assert body["criteria"]["location"]["country"] == "Spain"
    assert "Farmasi" in body["criteria"]["brands"]
    assert body["criteria"]["targetLeads"] == 25
    assert body["name"]


def test_an_empty_brief_is_refused(client):
    assert client.post("/searches/parse", json={"text": ""}).status_code == 422
