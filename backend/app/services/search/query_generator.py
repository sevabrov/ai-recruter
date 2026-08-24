"""
Query generation (spec §29).

One set of criteria is never one query, and — since the client asked for the
chosen country and languages to be requirements — never one language either.
Deterministic templates only, no LLM, which also means the generated set is
reproducible and reviewable: the wizard's preview and what the worker actually
fires are the same strings, because the wizard now asks the backend for them.

A plan is a query *plus the index to ask*. A Ukrainian query sent to the global
English index finds English pages about Ukraine — directories, company profiles,
"Top 10 MLM companies" listicles — which is exactly what the first live run came
back with. The language belongs to the query, not to the search.

`AIQueryGenerator` can later implement the same interface behind a flag.
"""

from collections.abc import Callable
from dataclasses import dataclass
from itertools import zip_longest
from typing import Protocol

from app.models.common import SourceKind
from app.models.search import SearchCriteria
from app.services.search import phrasebook
from app.services.search.markets import language_code

SITE_BY_SOURCE: dict[SourceKind, str] = {
    SourceKind.INSTAGRAM_PUBLIC: "site:instagram.com",
    SourceKind.LINKEDIN_PUBLIC: "site:linkedin.com/in",
    SourceKind.FACEBOOK_PUBLIC: "site:facebook.com",
    SourceKind.THREADS_PUBLIC: "site:threads.net",
}


@dataclass(frozen=True)
class QueryPlan:
    """One query and the index it should be asked against."""

    query: str
    #: A provider language code (`uk`, `es`), or None for "whatever the market is".
    language: str | None = None


class QueryGenerator(Protocol):
    def generate(self, criteria: SearchCriteria, limit: int = 12) -> list[QueryPlan]: ...


class TemplateQueryGenerator(QueryGenerator):
    def generate(self, criteria: SearchCriteria, limit: int = 12) -> list[QueryPlan]:
        seen: set[str] = set()
        negatives = " ".join(f'-"{word}"' for word in criteria.negative_keywords[:2])
        by_language: list[list[QueryPlan]] = []

        # The user's own wording first: it is the one language we know is right,
        # and dropping it because a translation exists would be presumptuous.
        for language in [None, *self._languages(criteria)]:
            plans: list[QueryPlan] = []

            def push(*parts: str | None, language: str | None = language, into=plans) -> None:
                query = " ".join(_deduplicated(parts))
                if not query or query in seen:
                    return
                seen.add(query)
                text = f"{query} {negatives}".strip() if negatives else query
                into.append(QueryPlan(text, language))

            self._for_language(criteria, language, push)
            if plans:
                by_language.append(plans)

        return _interleave(by_language)[:limit]

    # ------------------------------------------------------------------ per language
    def _for_language(
        self, criteria: SearchCriteria, language: str | None, push: Callable[..., None]
    ) -> None:
        place = self._place(criteria, language)
        if language and place is None:
            # No way to name the place in this language: the query would be the
            # English one with a foreign index attached, which is not a question
            # anybody asks. The market parameter alone already covers that case.
            return

        keywords = self._keywords(criteria, language)
        industries = self._words(criteria.industry, language, "beauty") or ["beauty"]
        business = self._words(criteria.business_types, language, "network marketing") or [
            "network marketing"
        ]
        distributor = phrasebook.term(language, "distributor") or "distributor"
        leader = phrasebook.term(language, "team leader") or "team leader"

        def phrase(*terms: str) -> str:
            """
            An exact phrase in the client's own words; separate exact terms in
            translation. `"beauty team leader"` is a phrase somebody writes;
            `"краса лідер команди"` is three translations in a row, and asking a
            search engine for it verbatim is asking for nothing.
            """
            if language is None:
                return f'"{" ".join(terms)}"'
            return " ".join(f'"{term}"' for term in terms)

        for source in criteria.sources:
            site = SITE_BY_SOURCE.get(source)
            if not site:
                continue
            push(site, f'"{keywords[0]}"', place)
            if len(keywords) > 1:
                push(site, f'"{keywords[1]}"', industries[0], place)

        push(phrase(keywords[0], distributor), place)
        push(phrase(industries[0], leader), f'"{business[0]}"', place)
        push(f'"{business[0]}"', industries[0], place, leader)

        if SourceKind.COMPANY_WEBSITES in criteria.sources:
            push(f'"{keywords[0]}"', distributor, place, "-shop", "-tienda")
        if SourceKind.BLOGS in criteria.sources:
            push(f'"{industries[0]}"', f'"{business[0]}"', "blog", place)

    # ------------------------------------------------------------------- ingredients
    @staticmethod
    def _languages(criteria: SearchCriteria) -> list[str]:
        """
        The languages worth writing a query in. English is left out: the untagged
        queries above are already in it, and asking the same words twice would
        spend a call on a duplicate.
        """
        codes: list[str] = []
        for language in criteria.languages:
            code = language_code(language)
            if code and code != "en" and code not in codes:
                codes.append(code)
        return codes

    @staticmethod
    def _place(criteria: SearchCriteria, language: str | None) -> str | None:
        location = criteria.location
        if language is None:
            if location.city:
                return f"{location.city} {location.country or ''}".strip()
            return location.country or ""

        city = phrasebook.place(language, location.city) if location.city else None
        country = phrasebook.place(language, location.country)
        if city and country:
            return f"{city} {country}"
        return city or country

    def _keywords(self, criteria: SearchCriteria, language: str | None) -> list[str]:
        keywords = self._words(criteria.keywords, language, "network marketing")
        return keywords or ["network marketing"]

    @staticmethod
    def _words(values: list[str], language: str | None, fallback: str) -> list[str]:
        """
        The client's words, translated where the phrasebook knows them. A brand
        name ("MIHI") has no translation and needs none — it is spelled the same
        in every market, which is exactly why it makes a good keyword.
        """
        if language is None:
            return list(values)
        translated = [phrasebook.term(language, value.strip().lower()) or value for value in values]
        if not translated:
            fallback_term = phrasebook.term(language, fallback)
            return [fallback_term] if fallback_term else []
        return translated


def _deduplicated(parts: tuple[str | None, ...]) -> list[str]:
    """
    Drop a part the query already says. "beauty" as a keyword and "Beauty" as the
    industry are one word to a search engine, and in translation they collapse
    outright — `"красота" красота Украина` was a real generated query.
    """
    kept: list[str] = []
    seen: set[str] = set()
    for part in parts:
        cleaned = " ".join((part or "").split())
        if not cleaned:
            continue
        key = cleaned.strip('"').casefold()
        if key in seen:
            continue
        seen.add(key)
        kept.append(cleaned)
    return kept


def _interleave(groups: list[list[QueryPlan]]) -> list[QueryPlan]:
    """
    Round-robin, so a limit cuts every language equally.

    Concatenating instead would spend the whole allowance on the first language
    and send none of the Ukrainian queries — the ones the search was actually
    asked for — which is the same failure as not translating them at all.
    """
    return [plan for row in zip_longest(*groups) for plan in row if plan is not None]
