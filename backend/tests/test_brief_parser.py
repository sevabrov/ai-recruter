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
    "requirements": [
        {
            "kind": "mlm",
            "label": "Досвід у МЛМ",
            "description": "",
            "terms": [],
            "importance": "required",
        },
        {
            "kind": "leadership",
            "label": "Має свою команду",
            "description": "",
            "terms": ["команда"],
            "importance": "high",
        },
    ],
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
    # The model's words first; a thin network-marketing list is filled up after them.
    assert criteria.keywords[:2] == ["мережевий маркетинг", "лідер команди"]
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
            "requirements": [
                {"kind": "mlm", "label": "МЛМ", "importance": "required"},
                {"kind": "telepathy", "label": "Mind reading", "importance": "required"},
            ],
            "sources": ["instagram_public", "myspace"],
            "keywords": ["медсестра", "a whole sentence that nobody writes in a bio ever"],
            "target_leads": 5000,
        },
        "brief",
    )

    assert criteria.location.country is None
    assert criteria.languages == ["Ukrainian", "English"]
    assert criteria.industry == ["Cosmetics"]
    assert [r.id for r in criteria.requirements] == [SignalType.MLM]
    assert criteria.sources == [SourceKind.INSTAGRAM_PUBLIC]
    assert criteria.keywords[0] == "медсестра"
    assert "a whole sentence that nobody writes in a bio ever" not in criteria.keywords
    assert criteria.target_leads == 1000


def test_a_cyrillic_brand_also_gets_its_latin_name():
    """`фармасі` and `farmasi` are two queries reaching two sets of people."""
    criteria = build_criteria({"brands": ["Фармасі", "MyLocalBrand"]}, "brief")

    assert criteria.brands == ["Фармасі", "Farmasi", "MyLocalBrand"]


def test_requirements_are_written_for_the_search_and_share_100_points():
    criteria = build_criteria(
        {
            "country": "PL",
            "keywords": ["Python developer"],
            "requirements": [
                {
                    "kind": "custom",
                    "label": "Python",
                    "terms": ["Python"],
                    "importance": "required",
                },
                {"kind": "custom", "label": "Django", "terms": ["Django"], "importance": "high"},
                {"kind": "custom", "label": "Senior", "terms": ["senior"], "importance": "normal"},
                {"kind": "custom", "label": "Python", "importance": "normal"},  # repeated
                {"kind": "telepathy", "label": "Mind reading"},  # not a kind
            ],
        },
        "brief",
    )
    requirements = criteria.requirements

    assert [r.id for r in requirements] == ["r1", "r2", "r3", "location"]
    assert [r.label for r in requirements[:3]] == ["Python", "Django", "Senior"]
    # A place the brief restricts the search to is required, like the core skill.
    assert [r.required for r in requirements] == [True, False, False, True]
    assert requirements[-1].id == "location"
    assert sum(r.weight for r in requirements) == 100
    assert requirements[0].weight > requirements[1].weight > requirements[2].weight


def test_without_named_requirements_the_clients_words_become_one():
    """Nothing assumed about the niche: the search's own words are the requirement."""
    criteria = build_criteria({"keywords": ["медсестра"], "brands": ["Charité"]}, "brief")

    assert len(criteria.requirements) == 1
    only = criteria.requirements[0]
    assert only.label == "медсестра"
    assert only.terms == ["медсестра", "Charité"]
    assert only.weight == 100


def test_nothing_about_network_marketing_is_assumed():
    """The product recruits for any role; a search for developers needs no MLM gate."""
    criteria = build_criteria({}, "brief")

    assert criteria.must_have == []
    assert criteria.requirements == []
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

    # Not a network-marketing search and no country: the brand alone, on each platform.
    assert queries[0] == "site:instagram.com джерелія"
    assert "site:facebook.com джерелія" in queries


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

    assert any('"консультант"' in query for query in queries)
    # No role word added in English, and "distributor" in no language at all.
    assert not any("consultant" in query or "distribut" in query for query in queries)
    assert not any("дистриб" in query for query in queries)


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


def test_the_clients_own_company_is_not_searched_for():
    """ "People for my company MIHI": searching for MIHI would find their own team."""
    criteria = build_criteria({"about_me": "MIHI", "brands": ["MIHI", "Farmasi"]}, "brief")

    assert criteria.about_me == "MIHI"
    assert criteria.brands == ["Farmasi"]


def test_ukraine_or_europe_is_a_list_of_places_not_the_whole_world():
    criteria = build_criteria(
        {"countries": ["UA"], "region": "europe", "keywords": ["junior frontend developer"]},
        "brief",
    )

    assert criteria.location.country is None
    assert criteria.countries == ["Ukraine"]
    assert criteria.region == "europe"
    # Queries go to Ukraine first, then to Europe's largest markets.
    assert criteria.focus_countries() == ["Ukraine", "Poland", "Germany", "Spain"]
    assert criteria.in_allowed_place("Romania") is True
    assert criteria.in_allowed_place("Czech Republic") is True
    assert criteria.in_allowed_place("Indonesia") is False
    assert criteria.in_allowed_place(None) is None
    location = next(r for r in criteria.requirements if r.id == "location")
    assert location.required


def test_the_defining_requirement_is_required_even_when_the_model_marked_none():
    """Every lead must match: a search always has something a candidate must show."""
    criteria = build_criteria(
        {
            "requirements": [
                {"kind": "custom", "label": "English", "importance": "normal"},
                {"kind": "custom", "label": "Frontend", "importance": "high"},
            ]
        },
        "brief",
    )

    assert [(r.label, r.required) for r in criteria.requirements] == [
        ("English", False),
        ("Frontend", True),
    ]


def test_queries_are_written_for_each_country_and_aimed_at_it():
    criteria = build_criteria(
        {
            "countries": ["UA"],
            "region": "europe",
            "keywords": ["junior frontend developer"],
            "languages": ["en"],
            "sources": ["linkedin_public"],
        },
        "brief",
    )

    plans = TemplateQueryGenerator().generate(criteria, limit=24)

    # Every country first; its cities only after (`_for_cities`).
    assert [(p.query, p.country) for p in plans[:4]] == [
        ('site:linkedin.com/in "junior frontend developer" Ukraine', "Ukraine"),
        ('site:linkedin.com/in "junior frontend developer" Poland', "Poland"),
        ('site:linkedin.com/in "junior frontend developer" Germany', "Germany"),
        ('site:linkedin.com/in "junior frontend developer" Spain', "Spain"),
    ]
    assert ('site:linkedin.com/in "junior frontend developer" Kyiv', "Ukraine") in [
        (p.query, p.country) for p in plans[4:]
    ]


def test_a_role_word_alone_is_not_a_search_term():
    """Alone, "консультант" found law firms and tax advisers, not distributors."""
    criteria = build_criteria(
        {"keywords": ["консультант", "Дистриб’ютор", "консультант Farmasi", "млм"]}, "brief"
    )

    assert criteria.keywords == ["консультант Farmasi", "млм"]


def test_the_clients_own_company_is_not_searched_for_inside_a_phrase_either():
    criteria = build_criteria(
        {
            "about_me": "MIHI",
            "brands": ["MIHI"],
            "keywords": ["дистриб'ютор MIHI", "партнер MIHI", "мережевий маркетинг"],
        },
        "brief",
    )

    assert criteria.keywords == ["мережевий маркетинг"]


def test_a_thin_network_marketing_search_is_given_the_niche_s_own_names():
    """One keyword left after the filters found fourteen addresses and no lead."""
    criteria = build_criteria(
        {
            "about_me": "MIHI",
            "keywords": ["дистриб'ютор MIHI", "мережевий маркетинг"],
            "requirements": [{"kind": "mlm", "label": "МЛМ", "importance": "required"}],
        },
        "brief",
    )

    assert criteria.keywords == [
        "мережевий маркетинг",
        "млм",
        "сетевой маркетинг",
        "сетевой бизнес",
    ]


def test_only_the_role_is_a_gate_and_its_qualifiers_earn_points():
    """Five required requirements turned away 220 of 251 Python developers."""
    criteria = build_criteria(
        {
            "countries": ["UA", "PL"],
            "sources": ["linkedin_public"],
            "requirements": [
                {"kind": "custom", "label": "Python backend", "importance": "required"},
                {"kind": "custom", "label": "Django або FastAPI", "importance": "required"},
                {"kind": "custom", "label": "Рівень middle", "importance": "required"},
                {"kind": "custom", "label": "Англійська", "importance": "required"},
                {"kind": "location", "label": "Україна або Польща", "importance": "required"},
            ],
        },
        "brief",
    )

    assert [(r.label or r.id, r.importance.value) for r in criteria.requirements] == [
        ("Python backend", "required"),
        ("Django або FastAPI", "required"),
        ("Рівень middle", "high"),
        ("Англійська", "high"),
        ("Україна або Польща", "required"),
    ]
    assert sum(r.weight for r in criteria.requirements) == 100


def test_the_place_is_a_preference_where_profiles_rarely_state_it():
    """An Instagram bio seldom names a country; LinkedIn always does."""
    instagram = build_criteria(
        {"countries": ["UA"], "sources": ["instagram_public"], "keywords": ["SMM-менеджер"]},
        "brief",
    )
    linkedin = build_criteria(
        {"countries": ["UA"], "sources": ["linkedin_public"], "keywords": ["sales manager"]},
        "brief",
    )

    def place(criteria: SearchCriteria) -> str:
        return next(r for r in criteria.requirements if r.id == "location").importance.value

    assert place(instagram) == "high"
    assert place(linkedin) == "required"
    # The role itself is still a gate.
    assert any(r.required for r in instagram.requirements if r.id != "location")


def test_a_country_does_not_make_its_language_a_filter():
    """'From Ukraine' threw away 13 of 30 sales managers whose LinkedIn is in English."""
    from_ukraine = build_criteria({"countries": ["UA"], "languages": ["uk", "ru"]}, "brief")
    publishes = build_criteria({"languages": ["uk"], "language_required": True}, "brief")

    assert from_ukraine.languages == ["Ukrainian", "Russian"]
    assert from_ukraine.require_language is False
    assert publishes.require_language is True


def test_a_platform_name_is_not_a_search_term():
    criteria = build_criteria({"keywords": ["SMM-менеджер", "SMM", "Instagram", "рілси"]}, "brief")

    assert criteria.keywords == ["SMM-менеджер", "рілси"]


def test_a_profession_on_instagram_is_also_asked_with_a_portfolio():
    """'SMM-менеджер' alone found 109 agencies for 26 people."""
    criteria = build_criteria(
        {"keywords": ["SMM-менеджер"], "sources": ["instagram_public"], "languages": ["uk"]},
        "brief",
    )

    queries = [p.query for p in TemplateQueryGenerator().generate(criteria, limit=24)]

    # No country: asked where Ukrainian is written (`SearchCriteria.language_focus`).
    assert 'site:instagram.com "SMM-менеджер" "портфоліо" Україна' in queries
    assert 'site:instagram.com "SMM-менеджер" "портфоліо" Польща' in queries
