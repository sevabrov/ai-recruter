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

    assert {plan.language for plan in plans} == {None, "uk", "ru"}
    # The client's own wording is asked as written, without a language attached:
    # it is the one phrasing we know is what they meant.
    assert any(plan.language is None and "Ukraine" in plan.query for plan in plans)


def test_the_limit_is_shared_between_languages():
    """
    A cap that took the first N would spend the whole allowance on English and
    send none of the Ukrainian queries — the same failure as not translating.
    """
    plans = TemplateQueryGenerator().generate(criteria(), limit=6)

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
            }, quoted


def test_no_language_asked_for_means_the_queries_are_unchanged():
    plans = TemplateQueryGenerator().generate(criteria(languages=[]), limit=24)

    assert plans and all(plan.language is None for plan in plans)


def test_english_is_not_asked_twice():
    """The untagged queries are already English; a second set would pay for a copy."""
    plans = TemplateQueryGenerator().generate(criteria(languages=["English"]), limit=24)

    assert {plan.language for plan in plans} == {None}


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
