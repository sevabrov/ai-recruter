"""
Asking in the language the answer is written in (spec §29).

The first live search for Ukraine was written in English and put to the global
index. What came back was English pages *about* Ukraine — a company directory, a
"Top 10 MLM companies" listicle, a distributor in Croatia — and no amount of
filtering afterwards can recover a person the query never reached. The country
and the languages are the client's requirements, so they have to shape the
question, not just the sieve.

Two properties matter here and both are about not overreaching: the client's own
wording is always asked as written, and a language is only asked in when we can
actually name the place in it. A Ukrainian query with "Ukraine" spelled in
English is not a Ukrainian query.
"""

from app.models.common import SourceKind
from app.models.search import SearchCriteria
from app.services.extraction import language
from app.services.search import phrasebook
from app.services.search.query_generator import TemplateQueryGenerator


def criteria(**overrides) -> SearchCriteria:
    return SearchCriteria.model_validate(
        {
            "keywords": ["network marketing", "beauty"],
            "industry": ["beauty"],
            "business_types": ["network marketing"],
            "location": {"country": "Ukraine"},
            "languages": ["Ukrainian", "Russian"],
            "sources": [SourceKind.INSTAGRAM_PUBLIC.value, SourceKind.LINKEDIN_PUBLIC.value],
            **overrides,
        }
    )


def test_a_search_for_ukraine_is_also_asked_in_ukrainian():
    plans = TemplateQueryGenerator().generate(criteria(), limit=24)

    ukrainian = [plan for plan in plans if plan.language == "uk"]
    assert ukrainian, "the language the people write in was not asked in"
    assert any("Україна" in plan.query for plan in ukrainian)
    assert any("мережевий маркетинг" in plan.query for plan in ukrainian)


def test_each_query_carries_the_index_it_should_be_put_to():
    plans = TemplateQueryGenerator().generate(criteria(), limit=24)

    assert {plan.language for plan in plans} == {"uk", "ru"}

    # English gets its queries when English is one of the languages asked for, and
    # they are the untagged ones: the client's own wording, asked as written.
    plans = TemplateQueryGenerator().generate(
        criteria(languages=["English", "Ukrainian", "Russian"]), limit=24
    )

    assert {plan.language for plan in plans} == {None, "uk", "ru"}
    assert any(plan.language is None and "Ukraine" in plan.query for plan in plans)


def test_the_limit_is_shared_between_languages():
    """
    A cap that took the first N would spend the whole allowance on English and
    send none of the Ukrainian queries — the same failure as not translating.
    """
    plans = TemplateQueryGenerator().generate(
        criteria(languages=["English", "Ukrainian", "Russian"]), limit=6
    )

    assert len(plans) == 6
    assert {plan.language for plan in plans} == {None, "uk", "ru"}


def test_a_language_we_cannot_name_the_place_in_is_not_asked_in():
    """
    Sending "Ukraine" to the Ukrainian index is the English query with a foreign
    label on it. The market parameter already covers that; a duplicate query is
    just another billed call.
    """
    plans = TemplateQueryGenerator().generate(
        criteria(location={"country": "Iceland"}, languages=["Ukrainian"]), limit=24
    )

    assert {plan.language for plan in plans} == {None}


def test_a_translated_query_does_not_repeat_itself():
    """
    "beauty" as a keyword and "Beauty" as the industry are one word to a search
    engine, and in translation they collapse outright: `"красота" красота Украина`
    was a real generated query.
    """
    plans = TemplateQueryGenerator().generate(
        criteria(keywords=["beauty"], industry=["beauty"]), limit=24
    )

    for plan in plans:
        words = [word.strip('"').casefold() for word in plan.query.split()]
        assert len(words) == len(set(words)), plan.query


def test_translated_terms_are_asked_for_separately_not_as_one_phrase():
    """
    `"beauty team leader"` is a phrase somebody writes. `"краса лідер команди"` is
    three translations in a row, and asking for it verbatim is asking for nothing.
    """
    plans = TemplateQueryGenerator().generate(criteria(), limit=24)

    for plan in (plan for plan in plans if plan.language == "uk"):
        for quoted in plan.query.split('"')[1::2]:
            assert quoted in {
                "мережевий маркетинг",
                "краса",
                "дистриб'ютор",
                "лідер команди",
                "beauty",
                "MLM",
                "#мережевиймаркетинг",
            }, quoted


def test_no_language_asked_for_means_the_queries_are_unchanged():
    plans = TemplateQueryGenerator().generate(criteria(languages=[]), limit=24)

    assert plans and all(plan.language is None for plan in plans)


def test_english_is_not_asked_twice():
    """The untagged queries are already English; a second set would pay for a copy."""
    plans = TemplateQueryGenerator().generate(criteria(languages=["English"]), limit=24)

    assert {plan.language for plan in plans} == {None}


def test_english_is_not_asked_at_all_when_it_was_not_asked_for():
    """
    The untagged pass writes the client's words unchanged — English words, put to
    the English index. Running it for a Ukrainian search spent a quarter of the
    calls on `site:instagram.com "network marketing" Ukraine`, which is the widest
    phrase in the niche asked in the language of the niche's global brands: back
    came Network Marketing Pro, Network Marketing Quotes and Eric Worre, 17 of
    that run's 41 addresses and not one of them a person in Ukraine.
    """
    plans = TemplateQueryGenerator().generate(criteria(), limit=24)

    assert plans, "a search that asks for Ukrainian and Russian still asks"
    assert {plan.language for plan in plans} == {"uk", "ru"}
    assert not any("network marketing" in plan.query for plan in plans)


def test_a_language_with_no_phrasebook_still_leaves_the_client_a_query():
    """
    Dropping the untagged pass must not be able to drop *every* pass: a language
    we cannot write is not a reason to run a search with no queries in it.
    """
    plans = TemplateQueryGenerator().generate(criteria(languages=["Icelandic"]), limit=24)

    assert plans and {plan.language for plan in plans} == {None}


def test_the_industry_reaches_the_queries_that_do_the_finding():
    """
    The client chose Beauty, and it changed nothing about who was found: the
    industry reached only the open-web templates, which a social-only search
    switches off. It scored people it had no hand in finding.
    """
    plans = TemplateQueryGenerator().generate(criteria(keywords=[], industry=["beauty"]), limit=24)

    site_queries = [plan for plan in plans if plan.query.startswith("site:")]
    assert site_queries
    assert any("краса" in plan.query for plan in site_queries), "in the asked-for language"
    assert any("красота" in plan.query for plan in site_queries)


def test_a_role_word_is_asked_for_when_the_client_wrote_no_keyword():
    """
    With no keyword of their own the query falls back to the niche's generic name,
    which is precisely what the niche's brand accounts are called — 22 of 26
    candidates in one run were refused as organisations. A role word is what a
    person writes in their own bio and a brand page does not.
    """
    plans = TemplateQueryGenerator().generate(criteria(keywords=[]), limit=24)

    assert any('"мережевий маркетинг" консультант' in plan.query for plan in plans)
    assert any('"сетевой маркетинг" консультант' in plan.query for plan in plans)
    # "Distributor" is never searched for, in any language (the client's request).
    assert not any("дистриб" in plan.query for plan in plans)


# ------------------------------------------------------------ what a page speaks


def test_ukrainian_and_russian_are_told_apart_by_their_own_letters():
    assert language.detect("Дистриб'ютор косметики, Київ. Запрошую в команду") == ["Ukrainian"]
    # Nothing here is exclusively Russian either — but `і ї є ґ` are so common in
    # Ukrainian that a whole bio without one of them is evidence in itself.
    assert language.detect("Дистрибьютор косметики, Москва. Приглашаю в команду") == ["Russian"]


def test_a_latin_language_is_only_claimed_when_it_wins_outright():
    """
    Spanish and Portuguese share half their function words. A tie is this file
    being unable to tell, and saying nothing beats putting Portuguese on a
    Spaniard — the client filters on this.
    """
    assert language.detect("Soy distribuidora de belleza en España, mi equipo te espera") == [
        "Spanish"
    ]
    assert language.detect("beauty") == []


def test_the_index_tag_and_the_text_are_both_kept():
    """
    A crawler tags a whole page; a bio is one paragraph of it. A Ukrainian bio on
    a page tagged English is one person publishing in two languages.
    """
    spoken = language.spoken(["English"], "Привіт! Я дистриб'ютор, разом побудуємо команду")

    assert spoken == ["English", "Ukrainian"]


# ------------------------------------------------------- a brief from another market
#
# Measured on a search for Poland written by a Ukrainian-speaking client: the brands
# went out bare (`site:instagram.com Avon`) and came back with twenty official Avon
# accounts from twenty countries, and the brief's Ukrainian keywords went out inside
# Polish queries (`"мережевий маркетинг" Polska`) and came back empty.

POLAND = {
    "brands": ["Avon", "Farmasi", "Amway"],
    "keywords": [
        "мережевий маркетинг",
        "млм",
        "сетевой маркетинг",
        "дистриб'ютор Avon",
    ],
    "negative_keywords": ["магазин", "салон краси"],
    "industry": ["Beauty"],
    "business_types": ["MLM", "Network marketing"],
    "location": {"country": "Poland"},
    "languages": ["Polish", "Russian", "Ukrainian"],
    "sources": [SourceKind.INSTAGRAM_PUBLIC.value, SourceKind.FACEBOOK_PUBLIC.value],
}


def _in_poland(query: str) -> bool:
    return any(name in query for name in ("Polska", "Польша", "Польща"))


def test_a_brand_is_asked_for_its_people_in_the_country_searched():
    plans = TemplateQueryGenerator().generate(criteria(**POLAND), limit=24)
    queries = [plan.query for plan in plans]

    assert not any(query.split(" -")[0] == "site:instagram.com Avon" for query in queries)
    # Poland's own language goes first, and takes the first brand.
    assert plans[0].language == "pl"
    assert plans[0].query.startswith("site:instagram.com Avon konsultantka Polska")
    russian = [plan.query for plan in plans if plan.language == "ru"]
    assert any(" консультант Польша" in q for q in russian)


def test_a_brand_on_a_platform_is_asked_once_not_once_per_language():
    """`Avon консультант Польша` found the accounts `Avon konsultantka Polska` had."""
    plans = TemplateQueryGenerator().generate(criteria(**POLAND), limit=48)
    country_wide = [p.query.split(" -")[0] for p in plans if _in_poland(p.query)]

    for brand in POLAND["brands"]:
        for site in ("site:instagram.com", "site:facebook.com"):
            asked = [q for q in country_wide if q.startswith(f"{site} {brand} ")]
            assert len(asked) == 1, (brand, site, asked)


def test_a_keyword_naming_a_listed_brand_is_not_asked_on_its_own():
    """Seventeen of eighteen "дистриб'ютор Avon"-style queries returned nothing."""
    plans = TemplateQueryGenerator().generate(criteria(**POLAND), limit=200)

    assert not [p.query for p in plans if "дистриб" in p.query or "dystrybut" in p.query]


def test_the_country_s_cities_come_after_the_country():
    plans = TemplateQueryGenerator().generate(criteria(**POLAND), limit=200)
    queries = [plan.query for plan in plans]
    first_city = next(i for i, q in enumerate(queries) if "Warszawa" in q or "Варшава" in q)

    assert all(_in_poland(q) for q in queries[:first_city])
    assert "site:instagram.com Avon konsultantka Warszawa" in " ".join(queries)
    # Each brand and platform once per city, shared out between the languages.
    warsaw = [q for q in queries if "Warszawa" in q or "Варшава" in q]
    assert len(warsaw) == len(POLAND["brands"]) * 2


def test_the_whole_world_is_asked_where_the_languages_are_written():
    """
    A search with no place came back as twenty official brand accounts: with no
    country to write in Ukrainian, the brand went out bare.
    """
    plans = TemplateQueryGenerator().generate(
        criteria(**{**POLAND, "location": {}, "languages": ["Ukrainian", "Polish"]}), limit=96
    )

    assert not any(p.query.split(" -")[0] == "site:instagram.com Avon" for p in plans)
    # Home countries first, then the diasporas — each in the languages that brought it.
    countries = list(dict.fromkeys(plan.country for plan in plans))
    assert countries[:3] == ["Ukraine", "Poland", "United Kingdom"]
    assert {(p.language, p.country) for p in plans} >= {
        ("uk", "Ukraine"),
        ("pl", "Poland"),
        ("uk", "Poland"),
        ("pl", "United Kingdom"),
    }
    assert ("pl", "Ukraine") not in {(p.language, p.country) for p in plans}
    assert any("Avon консультант Україна" in p.query for p in plans) or any(
        "консультант Україна" in p.query for p in plans
    )


def test_every_brand_survives_a_tight_query_cap():
    plans = TemplateQueryGenerator().generate(criteria(**POLAND), limit=12)
    queries = " ".join(plan.query for plan in plans)

    for brand in POLAND["brands"]:
        assert brand in queries
    # …and the cap still leaves room for the keyword templates.
    assert "marketing sieciowy" in queries


def test_a_brand_in_another_kind_of_search_gets_no_sales_word():
    plans = TemplateQueryGenerator().generate(
        criteria(
            brands=["Google"],
            keywords=["Python developer"],
            industry=[],
            business_types=[],
            location={"country": "Poland"},
            languages=["Polish"],
        ),
        limit=24,
    )

    assert "site:instagram.com Google Polska" in [plan.query for plan in plans]
    assert "konsultantka" not in " ".join(plan.query for plan in plans)


def test_the_brief_s_keywords_are_written_in_the_language_of_the_query():
    plans = TemplateQueryGenerator().generate(criteria(**POLAND), limit=24)
    polish = " ".join(plan.query for plan in plans if plan.language == "pl")
    russian = " ".join(plan.query for plan in plans if plan.language == "ru")

    assert '"marketing sieciowy" Polska' in polish
    assert "мережевий" not in polish and "сетевой" not in polish
    assert '"сетевой маркетинг" Польша' in russian
    assert "мережевий" not in russian


def test_exclusions_are_written_in_the_language_of_the_query():
    plans = TemplateQueryGenerator().generate(criteria(**POLAND), limit=24)

    for plan in plans:
        if plan.language == "pl":
            assert plan.query.endswith('-"sklep" -"salon kosmetyczny"')
        if plan.language == "ru":
            assert plan.query.endswith('-"магазин" -"салон красоты"')


def test_one_concept_written_three_ways_is_asked_once():
    plans = TemplateQueryGenerator().generate(criteria(**POLAND), limit=48)
    polish = [plan.query for plan in plans if plan.language == "pl"]

    # "мережевий маркетинг" and "сетевой маркетинг" are one Polish phrase.
    instagram = [q for q in polish if q.startswith('site:instagram.com "marketing sieciowy"')]
    assert len(instagram) == 1


def test_a_keyword_is_translated_around_a_name_but_not_around_a_common_word():
    assert phrasebook.translate("pl", "консультант Avon") == "konsultantka Avon"
    assert phrasebook.translate("pl", "Консультант Avon") == "konsultantka Avon"
    # "Distributor" is not a word the phrasebook writes any more.
    assert phrasebook.translate("pl", "дистриб'ютор Avon") is None
    assert phrasebook.translate("pl", "МЛМ") == "MLM"
    # "uroda blogger" would be two languages in one phrase.
    assert phrasebook.translate("pl", "beauty blogger") is None
    assert phrasebook.translate("pl", "Python developer") is None


def test_distributor_is_never_searched_for():
    """At the client's request: not as a template word, not as a keyword of theirs."""
    plans = TemplateQueryGenerator().generate(
        criteria(
            keywords=["дистриб'ютор млм", "Vertriebspartnerin", "мережевий маркетинг"],
            sources=[
                SourceKind.INSTAGRAM_PUBLIC.value,
                SourceKind.PUBLIC_WEB.value,
                SourceKind.COMPANY_WEBSITES.value,
            ],
            languages=["Ukrainian", "Russian", "Polish", "Spanish", "German", "English"],
        ),
        limit=500,
    )
    text = " ".join(plan.query for plan in plans).casefold()

    for root in ("distribu", "dystrybu", "дистриб", "vertriebspartner"):
        assert root not in text


# ------------------------------------------------------------ excluded countries


def test_russia_and_belarus_are_excluded_unless_taken_off_the_list():
    assert criteria().excluded_countries == ["Russia", "Belarus"]
    world = criteria(location={}, languages=["Russian"])

    countries = {plan.country for plan in TemplateQueryGenerator().generate(world, limit=96)}
    assert "Russia" not in countries and "Belarus" not in countries
    # Russian is still asked where it is written outside them.
    assert {"Kazakhstan", "Ukraine", "Germany"} <= countries

    allowed = criteria(location={}, languages=["Russian"], excluded_countries=[])
    countries = {plan.country for plan in TemplateQueryGenerator().generate(allowed, limit=96)}
    assert "Russia" in countries


def test_a_country_the_client_chose_is_never_excluded():
    chosen = criteria(location={"country": "Russia"})
    assert chosen.excluded_countries == ["Belarus"]


def test_the_client_may_exclude_another_country():
    world = criteria(location={}, languages=["Ukrainian"], excluded_countries=["Russia", "Germany"])

    countries = {plan.country for plan in TemplateQueryGenerator().generate(world, limit=96)}
    assert "Germany" not in countries and "Ukraine" in countries
