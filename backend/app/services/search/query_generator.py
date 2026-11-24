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

import re
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

        def pass_for(
            scoped: SearchCriteria, language: str | None, turn: int, of: int
        ) -> tuple[list[QueryPlan], list[QueryPlan]]:
            """This language's queries for this country: the first tier, and the depth."""
            country = scoped.location.country if several else None
            # An exclusion is a word too: `-"салон краси"` on a Polish query
            # excludes nothing, `-"salon kosmetyczny"` does.
            excluded = self._words(scoped.negative_keywords[:2], language, "")
            negatives = " ".join(f'-"{word}"' for word in excluded)

            def collector(plans: list[QueryPlan]) -> Callable[..., None]:
                def push(*parts: str | None) -> None:
                    query = " ".join(_deduplicated(parts))
                    if not query or query in seen:
                        return
                    seen.add(query)
                    text = f"{query} {negatives}".strip() if negatives else query
                    plans.append(QueryPlan(text, language, country))

                return push

            branded: list[QueryPlan] = []
            templated: list[QueryPlan] = []
            deeper: list[QueryPlan] = []
            self._for_brands(scoped, language, collector(branded), turn, of)
            self._for_language(scoped, language, collector(templated))
            self._for_cities(scoped, language, collector(deeper), turn, of)
            # Alternated, so the query cap keeps some of each.
            return _interleave([branded, templated]), deeper

        def for_country(
            scoped: SearchCriteria, passes: list[str | None]
        ) -> tuple[list[QueryPlan], list[QueryPlan]]:
            tiers = [
                pair
                for turn, language in enumerate(passes)
                if any(pair := pass_for(scoped, language, turn, len(passes)))
            ]
            if not tiers:
                # Every chosen language was one the phrasebook cannot write. The
                # client's own words, untranslated, are better than no query at all.
                tiers = [pair] if any(pair := pass_for(scoped, None, 0, 1)) else []
            return (
                _interleave([first for first, _ in tiers]),
                _interleave([deeper for _, deeper in tiers]),
            )

        scopes = self._scopes(criteria)
        several = len(scopes) > 1 or bool(criteria.language_focus())
        tiers = [for_country(scoped, passes) for scoped, passes in scopes]
        # Every country's first tier before anybody's depth: a city query is worth
        # asking only once its country has been asked.
        planned = [
            *_interleave([first for first, _ in tiers]),
            *_interleave([deeper for _, deeper in tiers]),
        ]

        room = max(0, limit - len(written))
        return [*written, *planned[:room]]

    def _scopes(self, criteria: SearchCriteria) -> list[tuple[SearchCriteria, list[str | None]]]:
        """
        The countries this search is asked in, each with the languages to ask it in.

        * one country: every language chosen;
        * several ("Ukraine or Europe"), country by country, because people write
          the country they are in, never the region. The first keeps every language
          chosen; past it, a Ukrainian query about Germany ("Німеччина") is not how
          anybody in Germany writes where they are, so only English and the
          country's own language are asked;
        * none — the whole world — the countries the chosen languages are written in
          (`SearchCriteria.language_focus`), each asked in the languages that
          brought it: Ukrainian in Ukraine, Poland and Germany; Polish in Poland,
          the United Kingdom and Germany.
        """

        def located(name: str) -> SearchCriteria:
            return criteria.model_copy(
                update={"location": criteria.location.model_copy(update={"country": name})}
            )

        world = criteria.language_focus()
        if world:
            return [
                (located(country), _own_first(_codes(languages) or [None], country))
                for country, languages in world
            ]
        if not (criteria.countries or criteria.region):
            return [(criteria, _own_first(self._passes(criteria), criteria.location.country))]
        scopes: list[tuple[SearchCriteria, list[str | None]]] = []
        for index, name in enumerate(criteria.focus_countries()):
            scoped = located(name)
            passes = self._passes(scoped)
            if index:
                own = COUNTRY_LANGUAGE.get(name)
                passes = [language for language in passes if language in (None, "en", own)]
            scopes.append((scoped, _own_first(passes, name)))
        return scopes

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
        for raw in criteria.custom_queries[:limit]:
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

    # ------------------------------------------------------------------------ brands
    def _for_brands(
        self,
        criteria: SearchCriteria,
        language: str | None,
        push: Callable[..., None],
        turn: int = 0,
        of: int = 1,
    ) -> None:
        """
        The brands the client named, asked for the people who sell them.

        A bare brand used to go out as it was typed, and `site:instagram.com Avon`
        for a search in Poland came back with twenty official Avon accounts:
        UK, Türkiye, the Philippines, Brazil, Mexico. The provider's country
        parameter only ranks, it does not filter, so the place has to be in
        the words.

        The place alone is not enough either: `Avon Polska` found Avon Polska,
        its shops and its fan pages. The same query with the word a rep puts in
        her own bio, `Avon konsultantka Polska`, found a page of Polish
        consultants. That word is added only to a network-marketing search;
        a brand in any other search is asked with its place alone.

        Each brand on each platform is asked **once**, in one of the search's
        languages (`turn` of `of`): `Avon консультант Польша` came back with the
        same Polish accounts `Avon konsultantka Polska` had, so asking every brand
        in every language spent two calls in three on addresses already found.
        Brands alternate platforms, so a query cap still asks for every brand.
        """
        brands = _brands(criteria)
        place = self._place(criteria, language)
        if not brands or (language and place is None):
            return
        role = self._role(criteria, language)
        for index, (brand, target) in enumerate(_pairs(brands, _targets(criteria))):
            if index % of == turn:
                push(target, brand, role, place)

    def _for_cities(
        self,
        criteria: SearchCriteria,
        language: str | None,
        push: Callable[..., None],
        turn: int = 0,
        of: int = 1,
    ) -> None:
        """
        Depth: the same questions asked of the country's largest cities.

        A search for fifty leads in Poland ran out of people after 48 queries: the
        country-wide ones all returned the same few dozen accounts, and Brave gives
        twenty results a question. A city is a different question with a different
        twenty — and how a consultant actually writes where she is ("Konsultantka
        AVON - Świebodzice", "Avon Lider Luboń/Poznań").

        Asked after every country's first tier (`generate`), shared out between the
        languages like the brands are, so no city is asked twice.
        """
        if language is None and None not in self._passes(criteria):
            return  # the untagged pass is only a fallback here: no English city names
        names = phrasebook.cities(language, criteria.location.country)
        if not names:
            return
        targets = _targets(criteria)
        brands = _brands(criteria)
        role = self._role(criteria, language)
        if brands:
            subjects = [(brand, role) for brand in brands]
        else:
            keywords = (
                self._keywords(criteria, language)
                if is_network_marketing(criteria)
                else self._words(_searchable(criteria), language, "")
            )
            subjects = [(f'"{keywords[0]}"', None)] if keywords else []
        # Each city starts the share-out one language further on, so a language
        # asks a different brand in each city rather than the same one everywhere.
        for shift, city in enumerate(names):
            for index, ((subject, said), target) in enumerate(_pairs(subjects, targets)):
                if (index + shift) % of == turn:
                    push(target, subject, said, city)

    def _role(self, criteria: SearchCriteria, language: str | None) -> str | None:
        """The word a seller of a brand calls herself, for a network-marketing search."""
        if not is_network_marketing(criteria):
            return None
        if language:
            return phrasebook.term(language, "consultant")
        # The untagged pass is English only when English was asked for; otherwise
        # it is a fallback, and an English word would not help.
        return "consultant" if None in self._passes(criteria) else None

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
        # "мережевий маркетинг" consultant Beauty mixed two languages in one query
        # and found next to nothing.
        words = language or next(iter(detect_codes(keywords[0])), None)
        industries = self._words(criteria.industry, words, "beauty") or ["beauty"]
        business = self._words(criteria.business_types, words, "network marketing") or [
            "network marketing"
        ]
        # The client asked that "distributor" and its cognates never be searched for.
        consultant = phrasebook.term(words, "consultant") or "consultant"
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
            #   * a role word. "Consultant" is what a person puts in their own
            #     bio and what a brand page does not.
            if criteria.industry:
                push(site, f'"{keywords[0]}"', industries[0], place)
            push(site, f'"{keywords[0]}"', consultant, place)

        # Open-web templates, and only when the client asked for the open web. They
        # carry no `site:` operator, so with three social sources selected they were
        # a third of the calls spent outside the sources — which is how a legal
        # journal's article about network marketing became a run's only lead.
        if not _WEB_SOURCES & set(criteria.sources):
            self._more_keywords(criteria, keywords, place, push)
            return

        push(phrase(keywords[0], consultant), place)
        push(phrase(industries[0], leader), f'"{business[0]}"', place)
        push(f'"{business[0]}"', industries[0], place, leader)

        if SourceKind.COMPANY_WEBSITES in criteria.sources:
            push(f'"{keywords[0]}"', consultant, place, "-shop", "-tienda")
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
        keywords = self._words(_searchable(criteria), language, "")
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
        keywords = self._words(_searchable(criteria), language, "network marketing")
        return keywords or ["network marketing"]

    @staticmethod
    def _words(values: list[str], language: str | None, fallback: str) -> list[str]:
        """
        The client's words, translated where the phrasebook knows them. A brand
        name ("MIHI") has no translation and needs none — it is spelled the same
        in every market, which is exactly why it makes a good keyword.

        The words are recognised in whatever language the brief was written in,
        so "мережевий маркетинг", "млм" and "сетевой маркетинг" all become
        "marketing sieciowy" or "MLM" for Poland — and are asked once, not three
        times.
        """
        if language is None:
            return list(values)
        translated = [phrasebook.translate(language, value) or value for value in values]
        if not translated:
            fallback_term = phrasebook.term(language, fallback)
            return [fallback_term] if fallback_term else []
        unique: dict[str, str] = {}
        for word in translated:
            unique.setdefault(word.casefold(), word)
        return list(unique.values())


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


def _brands(criteria: SearchCriteria) -> list[str]:
    """The brands as the client typed them, once each."""
    return [
        brand
        for brand in dict.fromkeys(" ".join(raw.split()) for raw in criteria.brands if raw)
        if brand
    ]


def _searchable(criteria: SearchCriteria) -> list[str]:
    """
    The client's keywords that are worth a query of their own.

    * Not one that names a brand they also listed: "дистриб'ютор Avon",
      "дистриб'ютор Farmasi", "дистриб'ютор Amway" became eighteen queries across
      three languages and seventeen returned nothing — the brand queries already
      ask for exactly these people in the words they do write.
    * Not one built on "distributor" or a cognate, in any language: the client
      asked that the word never be searched for.
    """
    names = [re.compile(rf"(?<!\w){re.escape(brand)}(?!\w)", re.I) for brand in _brands(criteria)]
    return [
        keyword
        for keyword in criteria.keywords
        if not any(n.search(keyword) for n in names) and not _DISTRIBUTOR.search(keyword)
    ]


#: "Distributor" in every spelling a brief arrives in — never searched for.
_DISTRIBUTOR = re.compile(r"distribu|dystrybu|дистриб|дистрибу|vertriebspartner", re.I)


def _targets(criteria: SearchCriteria) -> list[str | None]:
    """
    The `site:` operators a generated query is asked with. With the open web among
    the sources a bare query is a fair question; without it, every query names a
    platform — as with the client's own queries.
    """
    sites = [site for source in criteria.sources if (site := SITE_BY_SOURCE.get(source))]
    return list(sites) if sites and not (_WEB_SOURCES & set(criteria.sources)) else [None]


def _pairs(subjects: list, targets: list[str | None]) -> list[tuple]:
    """
    Every subject on every platform, ordered so that the platforms alternate:
    Avon on Instagram, Farmasi on Facebook, Amway on Instagram, Avon on Facebook…
    A cap that keeps the first few then still covers every subject.
    """
    pairs = []
    for index in range(len(subjects) * len(targets)):
        row, column = divmod(index, len(subjects))
        pairs.append((subjects[column], targets[(column + row) % len(targets)]))
    return pairs


def _own_first(passes: list[str | None], country: str | None) -> list[str | None]:
    """
    The country's own language first, when it is among those chosen. It gets the
    first share of the brands and its queries go out first: Polish consultants
    write "Avon konsultantka", and that was the best query a Polish search had.
    """
    own = COUNTRY_LANGUAGE.get(country or "")
    return sorted(passes, key=lambda language: language != own) if own in passes else passes


def _codes(languages: list[str]) -> list[str | None]:
    """Provider language codes for a list of language names; English is the untagged pass."""
    codes: list[str | None] = []
    for name in languages:
        code = language_code(name)
        if code is None:
            continue
        value = None if code == "en" else code
        if value not in codes:
            codes.append(value)
    return codes


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
