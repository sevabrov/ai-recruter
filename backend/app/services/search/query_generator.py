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

from app.models.common import SignalType, SourceKind
from app.models.search import SearchCriteria
from app.services.extraction.language import detect_codes
from app.services.search import phrasebook
from app.services.search.markets import language_code

SITE_BY_SOURCE: dict[SourceKind, str] = {
    SourceKind.INSTAGRAM_PUBLIC: "site:instagram.com",
    SourceKind.LINKEDIN_PUBLIC: "site:linkedin.com/in",
    SourceKind.FACEBOOK_PUBLIC: "site:facebook.com",
    SourceKind.THREADS_PUBLIC: "site:threads.net",
}

#: A hashtag is how somebody labels themselves, so generated hashtag queries looked
#: obviously right — and measurement said otherwise: all six of them, across
#: Instagram and Threads, returned exactly zero results. A quoted `"#tag"` inside a
#: `site:` query is not something the search index answers, so a third of that
#: run's billed calls bought nothing.
#:
#: Hashtags therefore live in `criteria.custom_queries`, where the client writes the
#: form that works for their market and can see immediately whether it returns
#: anything. Generating them here would be spending money on a shape we have
#: measured as empty.

#: Platforms where a profession is mostly advertised by agencies and studios.
_SOCIAL_SOURCES = {SourceKind.INSTAGRAM_PUBLIC, SourceKind.FACEBOOK_PUBLIC}

#: The word a freelancer puts in their bio and an agency rarely does, per language.
#: "SMM-менеджер" alone on Instagram returned 109 agencies, studios and courses
#: for 26 people; a person shows their own work.
PORTFOLIO = {
    "uk": "портфоліо",
    "ru": "портфолио",
    "en": "portfolio",
    "pl": "portfolio",
    "de": "Portfolio",
    "es": "portafolio",
    "it": "portfolio",
    "pt": "portfólio",
    "fr": "portfolio",
}

#: Languages a Cyrillic word may be written in when no letter tells them apart.
_CYRILLIC = {"uk", "ru", "bg"}

#: The sources that mean "anywhere on the indexed web". Without one of these
#: selected, no query may go out without a `site:` operator.
_WEB_SOURCES = {SourceKind.PUBLIC_WEB, SourceKind.COMPANY_WEBSITES, SourceKind.BLOGS}


@dataclass(frozen=True)
class QueryPlan:
    """One query and the index it should be asked against."""

    query: str
    #: A provider language code (`uk`, `es`), or None for "whatever the market is".
    language: str | None = None
    #: The country this query was written for, when a search asks for several; the
    #: provider is then aimed at that country's index for this query alone.
    country: str | None = None


class QueryGenerator(Protocol):
    def generate(self, criteria: SearchCriteria, limit: int = 12) -> list[QueryPlan]: ...


class TemplateQueryGenerator(QueryGenerator):
    def generate(self, criteria: SearchCriteria, limit: int = 12) -> list[QueryPlan]:
        written = self._written(criteria, limit)
        seen: set[str] = {plan.query for plan in written}
        negatives = " ".join(f'-"{word}"' for word in criteria.negative_keywords[:2])

        def pass_for(scoped: SearchCriteria, language: str | None) -> list[QueryPlan]:
            plans: list[QueryPlan] = []
            country = scoped.location.country if several else None

            def push(*parts: str | None) -> None:
                query = " ".join(_deduplicated(parts))
                if not query or query in seen:
                    return
                seen.add(query)
                text = f"{query} {negatives}".strip() if negatives else query
                plans.append(QueryPlan(text, language, country))

            self._for_language(scoped, language, push)
            return plans

        def for_country(scoped: SearchCriteria, first: bool) -> list[QueryPlan]:
            passes = self._passes(scoped)
            if several and not first:
                # A Ukrainian query about Germany ("Німеччина") is not how anybody in
                # Germany writes where they are. Past the first country, only English
                # and the country's own language are asked; the first keeps every
                # language chosen, which is where a diaspora search lives.
                own = COUNTRY_LANGUAGE.get(scoped.location.country or "")
                passes = [language for language in passes if language in (None, "en", own)]
            by_language = [plans for language in passes if (plans := pass_for(scoped, language))]
            if not by_language:
                # Every chosen language was one the phrasebook cannot write. The
                # client's own words, untranslated, are better than no query at all.
                by_language = [plans] if (plans := pass_for(scoped, None)) else []
            return _interleave(by_language)

        # "Ukraine or Europe" is asked country by country: people write the country
        # they are in, never the region. Several countries are interleaved, so the
        # query cap cuts each of them equally rather than dropping the last.
        several = bool(criteria.countries or criteria.region)
        if several:
            scopes = [
                criteria.model_copy(
                    update={"location": criteria.location.model_copy(update={"country": name})}
                )
                for name in criteria.focus_countries()
            ]
        else:
            scopes = [criteria]
        templates = _interleave(
            [for_country(scoped, index == 0) for index, scoped in enumerate(scopes)]
        )

        room = max(0, limit - len(written))
        return [*written, *templates[:room]]

    # -------------------------------------------------------------- the client's own
    @staticmethod
    def _written(criteria: SearchCriteria, limit: int) -> list[QueryPlan]:
        """
        Queries the client typed, ahead of everything generated.

        Templates cannot know that `site:instagram.com "#млмукраина"` is how the
        people they are looking for label themselves. Somebody who knows their
        market can write that in one line, so these are never dropped to make room
        for a template — the cap eats the generated ones instead.

        The language is read off the query itself, so a Cyrillic query reaches the
        Cyrillic index without anybody having to say so twice.

        A query with no `site:` operator inherits the search's sources. Written
        plainly, `джерелія` is a question to the whole indexed web, and a search
        restricted to social platforms then throws almost all of the answer away:
        two such queries returned 20 results — the brand's own site, four shops, a
        catalogue, an app-store listing and a hotel called Jerelia — of which 18
        were dropped for being off-source. The client meant "find me this on the
        platforms I chose", so that is what is asked. When the open web is among
        the sources, the bare query is a fair question and stays as written.
        """
        sites = [
            site for source in criteria.sources if (site := SITE_BY_SOURCE.get(source)) is not None
        ]
        scope_to_sites = bool(sites) and not (_WEB_SOURCES & set(criteria.sources))

        plans: list[QueryPlan] = []
        seen: set[str] = set()
        # A brand is asked exactly like a query the client wrote: bare, on each
        # chosen platform. Measured: `site:instagram.com джерелія` came back with a
        # page of the brand's distributors, where `"network marketing"` had come
        # back with the niche's famous accounts.
        for raw in [*criteria.brands, *criteria.custom_queries][:limit]:
            query = " ".join((raw or "").split())
            if not query:
                continue
            wanted = (
                [f"{site} {query}" for site in sites]
                if scope_to_sites and "site:" not in query.casefold()
                else [query]
            )
            # The language belongs to the words the client wrote, not to the
            # operator we prefixed, so it is detected once for the whole group.
            codes = detect_codes(query)
            for scoped in wanted:
                if scoped in seen:
                    continue
                seen.add(scoped)
                plans.append(QueryPlan(scoped, codes[0] if codes else None))
        return plans

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

        if not is_network_marketing(criteria):
            self._for_any_role(criteria, language, place, push)
            return

        keywords = self._keywords(criteria, language)
        # The words added around a keyword are written in the keyword's language.
        # "мережевий маркетинг" distributor Beauty mixed two languages in one query
        # and found next to nothing.
        words = language or next(iter(detect_codes(keywords[0])), None)
        industries = self._words(criteria.industry, words, "beauty") or ["beauty"]
        business = self._words(criteria.business_types, words, "network marketing") or [
            "network marketing"
        ]
        distributor = phrasebook.term(words, "distributor") or "distributor"
        leader = phrasebook.term(words, "team leader") or "team leader"

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
                continue
            # One keyword — and when the client wrote none, that one is the
            # niche's generic name, which is the widest question there is and
            # brings back the niche's brands rather than its people. Two things
            # narrow it, and both are things the client already told us:
            #
            #   * the industry they chose, which until now reached only the
            #     open-web templates — so a search restricted to social sources
            #     never used it to *find* anybody, only to score them;
            #   * a role word. "Consultant", "distributor" is what a person puts
            #     in their own bio and what a brand page does not.
            if criteria.industry:
                push(site, f'"{keywords[0]}"', industries[0], place)
            push(site, f'"{keywords[0]}"', distributor, place)

        # Open-web templates, and only when the client asked for the open web. They
        # carry no `site:` operator, so with three social sources selected they were
        # a third of the calls spent outside the sources — which is how a legal
        # journal's article about network marketing became a run's only lead.
        if not _WEB_SOURCES & set(criteria.sources):
            self._more_keywords(criteria, keywords, place, push)
            return

        push(phrase(keywords[0], distributor), place)
        push(phrase(industries[0], leader), f'"{business[0]}"', place)
        push(f'"{business[0]}"', industries[0], place, leader)

        if SourceKind.COMPANY_WEBSITES in criteria.sources:
            push(f'"{keywords[0]}"', distributor, place, "-shop", "-tienda")
        if SourceKind.BLOGS in criteria.sources:
            push(f'"{industries[0]}"', f'"{business[0]}"', "blog", place)
        self._more_keywords(criteria, keywords, place, push)

    def _for_any_role(
        self,
        criteria: SearchCriteria,
        language: str | None,
        place: str | None,
        push: Callable[..., None],
    ) -> None:
        """
        Templates for a search that is not about network marketing.

        Built only from what the client gave — their role words and, if they named
        one, an industry. Nothing from the network-marketing niche is added: a
        search for developers that appended "distributor" to every query, or fell
        back to "network marketing" when it had no keyword, would be asking for
        somebody else entirely. With no words of the client's own there is nothing
        to template; the brands (asked first, as written queries) carry the search.
        """
        keywords = self._words(criteria.keywords, language, "")
        if not keywords:
            return
        industries = self._words(criteria.industry, language, "")
        industry = industries[0] if industries else None
        second = keywords[1] if len(keywords) > 1 else None

        for source in criteria.sources:
            site = SITE_BY_SOURCE.get(source)
            if not site:
                continue
            push(site, f'"{keywords[0]}"', place)
            if source in _SOCIAL_SOURCES:
                # "SMM-менеджер" reads as Ukrainian and Russian alike; the
                # search's own languages break the tie.
                written = list(detect_codes(keywords[0]))
                if _CYRILLIC.intersection(written):
                    written += sorted(_CYRILLIC.difference(written))
                wanted = [language_code(name) for name in criteria.languages]
                code = language or next(
                    (c for c in wanted if c in written), next(iter(written), None)
                )
                if word := PORTFOLIO.get(code or ""):
                    push(site, f'"{keywords[0]}"', f'"{word}"', place)
            if second:
                push(site, f'"{second}"', industry, place)
            elif industry:
                push(site, f'"{keywords[0]}"', industry, place)

        if not _WEB_SOURCES & set(criteria.sources):
            self._more_keywords(criteria, keywords, place, push)
            return
        push(f'"{keywords[0]}"', place)
        if second:
            push(f'"{second}"', industry, place)
        if SourceKind.BLOGS in criteria.sources:
            push(f'"{keywords[0]}"', "blog", place)
        self._more_keywords(criteria, keywords, place, push)

    @staticmethod
    def _more_keywords(
        criteria: SearchCriteria,
        keywords: list[str],
        place: str | None,
        push: Callable[..., None],
    ) -> None:
        """
        The client's further words, each asked on its own on every platform.

        The templates above use the first two. A brief that names five ways these
        people describe themselves — "консультант", "дистриб'ютор", "бізнес-партнер"
        — was asking for all five, and a search that used two found forty addresses
        and ran out of candidates at four leads. Added after the templates, so the
        query cap trims these first.
        """
        for keyword in keywords[2:MAX_KEYWORD_QUERIES]:
            for source in criteria.sources:
                site = SITE_BY_SOURCE.get(source)
                if site:
                    push(site, f'"{keyword}"', place)

    # ------------------------------------------------------------------- ingredients
    @staticmethod
    def _passes(criteria: SearchCriteria) -> list[str | None]:
        """
        Which languages to write queries in, and in what order.

        The untagged pass writes the client's words unchanged — English, in
        practice, asked against the English index. Running it regardless of what
        was asked for is what spent a quarter of a Ukrainian search's calls on
        `site:instagram.com "network marketing" Ukraine`: the widest phrase in the
        niche, in the language of the niche's global brands. It came back with
        Network Marketing Pro, Network Marketing Quotes and Eric Worre — famous
        accounts, none of them a person in Ukraine, and 17 of that run's 41
        addresses.

        So it runs when English is one of the languages asked for, and when no
        language was named at all. Otherwise the money goes to the languages the
        client actually chose.
        """
        codes = TemplateQueryGenerator._languages(criteria)
        english = any(language_code(name) == "en" for name in criteria.languages)
        if english or not codes:
            return [None, *codes]
        return list(codes)

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


#: How many of the client's keywords become queries of their own.
MAX_KEYWORD_QUERIES = 5

#: The language a country's people write their location in, for searches over several.
COUNTRY_LANGUAGE: dict[str, str] = {
    "Ukraine": "uk",
    "Poland": "pl",
    "Germany": "de",
    "Austria": "de",
    "Switzerland": "de",
    "Spain": "es",
    "Italy": "it",
    "Portugal": "pt",
    "France": "fr",
    "Belgium": "fr",
    "Netherlands": "nl",
    "Czechia": "cs",
    "Romania": "ro",
    "United Kingdom": "en",
    "United States": "en",
}

#: How a search says it is about network marketing, in the words a brief or the
#: old wizard put into it. Business types are tokens; keywords are the client's.
_MLM_BUSINESS = {"mlm", "network marketing", "direct sales"}
_MLM_WORDS = (
    "network marketing",
    "mlm",
    "млм",
    "мережев",
    "сетев",
    "marketing multinivel",
    "netzwerkmarketing",
    "marketing sieciowy",
)


def is_network_marketing(criteria: SearchCriteria) -> bool:
    """
    Whether the network-marketing templates apply to this search.

    The product recruits for any role. The niche's vocabulary — "distributor",
    "team leader", a fallback to "network marketing" — is right for a search for
    distributors and wrong for everything else, so it is used only when the
    search itself says that is what it is: by business type, by the MLM signal,
    or in the client's own keywords.
    """
    if any(kind.casefold() in _MLM_BUSINESS for kind in criteria.business_types):
        return True
    if SignalType.MLM in criteria.must_have or SignalType.MLM in criteria.nice_to_have:
        return True
    if any(r.id == SignalType.MLM for r in criteria.requirements or []):
        return True
    return any(
        marker in keyword.casefold() for keyword in criteria.keywords for marker in _MLM_WORDS
    )


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
