"""
Free text → search criteria.

The wizard used to be five screens of fields, most of which the client could not
say what they did. It is now one question — "who are you, and who are you looking
for?" — answered in the client's own words, typed or pasted, in any language. This
module turns that answer into the same `SearchCriteria` the five screens produced,
so nothing downstream (queries, scoring, pricing) changes.

Two rules, both from what the old wizard got wrong:

* **The client's words stay in the client's language.** Brands and the phrases
  people use about themselves are search terms, and `джерелія` finds the people a
  Ukrainian client means where `network marketing` finds the niche's famous
  accounts. Only closed vocabularies — country, language, industry, signal,
  source — become tokens, and those are shown translated by the frontend.
* **What is missing is left empty, never invented.** A country the brief does not
  name is not guessed; the review screen asks for it. A guessed field looks
  exactly like an answered one, which is how a search ends up somewhere the client
  never asked to look.

`OpenAIBriefParser` does the reading. `RuleBriefParser` is the stand-in for when
no key is configured or the model is unavailable: it recognises countries,
languages, well-known brands and a lead count, and leaves the rest to the review
screen's questions — honest about what it could not read rather than wrong.
"""

import json
import re
from dataclasses import dataclass
from typing import Any, Protocol

import httpx

from app.core.errors import ProviderAuthError, ProviderError, ProviderUnavailableError
from app.core.logging import get_logger
from app.models.common import SignalType, SourceKind
from app.models.search import SearchCriteria
from app.services.brief.vocabulary import (
    BUSINESS_TYPES,
    COUNTRIES,
    INDUSTRIES,
    KNOWN_BRANDS,
    LANGUAGES,
)
from app.services.search.markets import COUNTRY_NAMES

log = get_logger(__name__)

#: Where to look when the brief names no platform: the three that return people.
#: The open web is left out on purpose — with no `site:` it is a third of the
#: calls spent on directories and articles (see the query generator).
DEFAULT_SOURCES: tuple[SourceKind, ...] = (
    SourceKind.INSTAGRAM_PUBLIC,
    SourceKind.FACEBOOK_PUBLIC,
    SourceKind.LINKEDIN_PUBLIC,
)

MAX_BRIEF = 4000


@dataclass
class ParsedBrief:
    name: str
    criteria: SearchCriteria
    #: Which parser produced this, so the screen can say when it was the stand-in.
    parser: str


class BriefParser(Protocol):
    name: str

    async def parse(self, text: str, locale: str) -> ParsedBrief: ...


# ------------------------------------------------------------------ normalising


def build_criteria(raw: dict[str, Any], brief: str) -> SearchCriteria:
    """
    A model's (or the rule parser's) answer, reduced to values the system accepts.

    Everything is filtered against a closed list or trimmed to a length, because a
    parser's output is input: a country code the markets do not know, a signal that
    does not exist or a forty-word "keyword" would otherwise travel straight into
    a billed query.
    """
    country = COUNTRIES.get(str(raw.get("country") or "").upper())
    languages = _unique(
        LANGUAGES[code] for code in _codes(raw.get("languages")) if code in LANGUAGES
    )
    industries = _pick(raw.get("industries"), INDUSTRIES)
    business = _pick(raw.get("business_types"), BUSINESS_TYPES)

    # Taken as the brief says, with nothing assumed: the product recruits for any
    # role, and a network-marketing requirement nobody asked for would refuse every
    # candidate of a search for, say, developers.
    signals = {signal.value: signal for signal in SignalType}
    must = _unique(signals[s] for s in _strings(raw.get("must_have")) if s in signals)
    nice = _unique(
        signals[s]
        for s in _strings(raw.get("nice_to_have"))
        if s in signals and signals[s] not in must
    )

    kinds = {kind.value: kind for kind in SourceKind}
    sources = _unique(kinds[s] for s in _strings(raw.get("sources")) if s in kinds)

    try:
        target = int(raw.get("target_leads") or 0)
    except (TypeError, ValueError):
        target = 0

    return SearchCriteria(
        brief=brief[:MAX_BRIEF],
        about_me=_text(raw.get("about_me"), 500),
        brands=_with_latin_names(_terms(raw.get("brands"), 6)),
        keywords=_terms(raw.get("keywords"), 8),
        negative_keywords=_terms(raw.get("negative_keywords"), 8),
        industry=industries,
        business_types=business,
        location={"country": country, "city": _text(raw.get("city"), 80) or None},
        languages=languages,
        must_have=must,
        nice_to_have=nice,
        sources=sources or list(DEFAULT_SOURCES),
        target_leads=max(0, min(1000, target)),
    )


def _with_latin_names(brands: list[str]) -> list[str]:
    """
    A known brand written in Cyrillic also gets its Latin name, right after it.

    The two spellings reach different people — `фармасі` and `farmasi` are two
    queries with two sets of results — and a model asked for both writes both only
    some of the time. Only the Latin name is added, not every spelling: each one
    is a billed query on every platform.
    """
    expanded: list[str] = []
    for brand in brands:
        expanded.append(brand)
        lowered = brand.casefold()
        for canonical, spellings in KNOWN_BRANDS.items():
            if lowered in spellings or lowered == canonical.casefold():
                expanded.append(canonical)
                break
    return _unique(expanded)[:10]


def _strings(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [
        str(item).strip() for item in value if isinstance(item, str | int) and str(item).strip()
    ]


def _codes(value: Any) -> list[str]:
    return [item.lower().split("-")[0] for item in _strings(value)]


def _text(value: Any, limit: int) -> str:
    return " ".join(str(value or "").split())[:limit]


def _terms(value: Any, limit: int) -> list[str]:
    """Short phrases only: a sentence is not a search term."""
    kept = [" ".join(term.split()) for term in _strings(value)]
    return _unique(term for term in kept if 0 < len(term) <= 60 and len(term.split()) <= 5)[:limit]


def _pick(value: Any, allowed: tuple[str, ...]) -> list[str]:
    by_key = {entry.casefold(): entry for entry in allowed}
    return _unique(by_key[s.casefold()] for s in _strings(value) if s.casefold() in by_key)


def _unique(values) -> list:
    """First occurrence wins; `Farmasi` and `farmasi` are one search term."""
    kept: list = []
    seen: set = set()
    for value in values:
        key = value.casefold() if isinstance(value, str) else value
        if key not in seen:
            seen.add(key)
            kept.append(value)
    return kept


def _fallback_name(text: str) -> str:
    first = re.split(r"[.!?\n]", " ".join(text.split()) or "", maxsplit=1)[0]
    return (first[:57] + "…") if len(first) > 60 else first


# ------------------------------------------------------------------------ OpenAI

SYSTEM_PROMPT = """\
You turn a recruiter's free-text description of a people search into structured \
search criteria. The search can be for ANY kind of person: employees for any role or \
industry (developers, nurses, drivers, sales managers…), freelancers, partners, \
distributors for a network-marketing business, influencers. Adapt to what the text \
asks for; do not assume a niche it does not mention. The text may be in Ukrainian, \
Russian, English or any other language, and may have been dictated.

Rules:
- Never invent. If the text does not say something, leave that field empty ("" or [] \
or 0). The recruiter will be asked for whatever is missing.
- Keep the recruiter's own words in the language the wanted people write in. Do not \
translate brands, company names, job titles or self-descriptions into English unless \
those people would write them in English (many IT titles are written in English).
- about_me: who the recruiter is — only if they state their own company, brand, role \
or location ("I'm an HR at an IT company in Warsaw", "I'm a MIHI leader in Spain"), as \
a short phrase in the text's language; otherwise "". Never fill it with fragments of \
the request itself. The recruiter's OWN company or brand goes here, NOT into brands — \
unless they explicitly want people who already work there.
- brands: companies, brands or products the wanted people work at, represent or \
distribute, as named in the text. Write each the way people spell it in their \
profiles; if a brand is commonly written both in Latin and Cyrillic (e.g. Farmasi / \
Фармасі), include both spellings. Max 6.
- keywords: short phrases (1-3 words) the wanted people would write about themselves \
in their own profile: job titles, roles, skills, niche words — e.g. "Python developer", \
"Django", "медсестра", "менеджер з продажу", "консультант", "мережевий маркетинг". \
Only what the text implies. No brands, no places. Max 6.
- negative_keywords: kinds of pages or people to exclude, as words that appear on \
them ("агенція", "магазин", "вакансія"). Max 5.
- country: ISO 3166-1 alpha-2 code of the ONE country to search in, only if stated \
or unambiguous; otherwise "".
- city: a city only if stated, in the text's language; otherwise "".
- languages: ISO 639-1 codes of the languages the wanted people write in. Include \
languages that are stated, and the country's main language when a country is given. \
Diaspora matters: "Ukrainians in Spain" means uk and ru, and es.
- industries / business_types: only from the allowed values, and only if the text \
implies one of them; most searches will have none.
- must_have / nice_to_have: only signals the text actually asks for. mlm = works in \
network marketing (only for network-marketing searches); beauty = works in \
beauty/cosmetics; recruiting = actively invites people into a team; leadership = \
leads a team or people; location = is in the target place; personalBrand = has a \
visible personal brand; activity = posted recently. must_have only for what the text \
states as a hard requirement — every must_have is one more condition each candidate \
must visibly meet, so most searches need zero or one. Alternatives ("has a team OR \
recruits") are nice_to_have, not must_have. Never put location in must_have: the \
country is already enforced by a separate filter. Leave both empty if nothing applies.
- sources: the platforms named in the text. If none are named, choose where such \
people most likely have public profiles: linkedin_public for professional and office \
roles (IT, finance, engineering, management, HR, sales B2B); instagram_public and \
facebook_public for beauty, network marketing, local services, creators; combine when \
in doubt. Use public_web only if the text asks for websites, articles or companies.
- target_leads: how many leads/people are wanted, if a number is given; otherwise 0.
- name: a short name for this search (max 6 words) in the language of the interface \
locale given below."""


def response_schema() -> dict[str, Any]:
    """Strict JSON schema: every key present, nothing else, enums where closed."""

    def strings(enum: list[str] | None = None) -> dict[str, Any]:
        item: dict[str, Any] = {"type": "string"}
        if enum is not None:
            item["enum"] = enum
        return {"type": "array", "items": item}

    properties: dict[str, Any] = {
        "name": {"type": "string"},
        "about_me": {"type": "string"},
        "brands": strings(),
        "keywords": strings(),
        "negative_keywords": strings(),
        "industries": strings(list(INDUSTRIES)),
        "business_types": strings(list(BUSINESS_TYPES)),
        "country": {"type": "string", "enum": ["", *COUNTRIES]},
        "city": {"type": "string"},
        "languages": strings(list(LANGUAGES)),
        "must_have": strings([signal.value for signal in SignalType]),
        "nice_to_have": strings([signal.value for signal in SignalType]),
        "sources": strings([kind.value for kind in SourceKind]),
        "target_leads": {"type": "integer"},
    }
    return {
        "type": "object",
        "properties": properties,
        "required": list(properties),
        "additionalProperties": False,
    }


class OpenAIBriefParser:
    """One structured call to the Chat Completions API. No SDK: one documented POST."""

    name = "openai"

    def __init__(
        self,
        api_key: str,
        *,
        model: str,
        endpoint: str = "https://api.openai.com/v1/chat/completions",
        timeout_seconds: float = 30.0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._key = api_key
        self._model = model
        self._endpoint = endpoint
        self._timeout = timeout_seconds
        self._client = client

    async def parse(self, text: str, locale: str) -> ParsedBrief:
        brief = text.strip()[:MAX_BRIEF]
        payload = {
            "model": self._model,
            "temperature": 0,
            "messages": [
                {"role": "system", "content": f"{SYSTEM_PROMPT}\nInterface locale: {locale}"},
                {"role": "user", "content": brief},
            ],
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": "search_brief",
                    "strict": True,
                    "schema": response_schema(),
                },
            },
        }
        raw = await self._post(payload)
        criteria = build_criteria(raw, brief)
        name = _text(raw.get("name"), 80) or _fallback_name(brief)
        log.info(
            "brief_parsed",
            extra={
                "parser": self.name,
                "brands": len(criteria.brands),
                "country": criteria.location.country,
            },
        )
        return ParsedBrief(name=name, criteria=criteria, parser=self.name)

    async def _post(self, payload: dict[str, Any]) -> dict[str, Any]:
        client = self._client or httpx.AsyncClient(timeout=httpx.Timeout(self._timeout))
        try:
            response = await client.post(
                self._endpoint,
                json=payload,
                headers={"Authorization": f"Bearer {self._key}"},
            )
        except httpx.HTTPError as error:
            raise ProviderUnavailableError(
                f"OpenAI request failed: {error}", provider=self.name
            ) from error
        finally:
            if self._client is None:
                await client.aclose()

        if response.status_code in (401, 403):
            raise ProviderAuthError("OpenAI rejected the API key", provider=self.name)
        if response.status_code >= 400:
            raise ProviderError(
                f"OpenAI answered {response.status_code}: {response.text[:300]}", provider=self.name
            )
        try:
            message = response.json()["choices"][0]["message"]
            if message.get("refusal"):
                raise ProviderError("The model refused to parse the brief", provider=self.name)
            return json.loads(message["content"])
        except (KeyError, IndexError, TypeError, ValueError) as error:
            raise ProviderError(
                "OpenAI returned an unreadable answer", provider=self.name
            ) from error


# ------------------------------------------------------------------ rule parser

#: Stems, because Ukrainian and Russian inflect: "українською", "украинский".
LANGUAGE_STEMS: dict[str, tuple[str, ...]] = {
    # "україно" is the first half of "україно- та російськомовні" (and of
    # "українок": Ukrainian women write in Ukrainian).
    "uk": ("українськ", "украинск", "ukrainian", "україно", "украино"),
    "ru": ("російськ", "русск", "russian", "російськомовн", "русскоязычн", "русскоговорящ"),
    "en": ("англійськ", "английск", "english"),
    "es": ("іспанськ", "испанск", "spanish", "español"),
    "pl": ("польськ", "польск", "polish"),
    "de": ("німецьк", "немецк", "german", "deutsch"),
    "it": ("італійськ", "итальянск", "italian"),
    "pt": ("португальськ", "португальск", "portuguese"),
    "fr": ("французьк", "французск", "french"),
    "ro": ("румунськ", "румынск", "romanian"),
    "cs": ("чеськ", "чешск", "czech"),
    "nl": ("нідерландськ", "голландськ", "голландск", "dutch"),
}

#: A few country spellings the location filter does not need but a brief uses.
EXTRA_COUNTRY_STEMS: dict[str, str] = {
    "іспані*": "Spain",
    "испани*": "Spain",
    "італі*": "Italy",
    "итали*": "Italy",
    "португалі*": "Portugal",
    "франці*": "France",
    "франци*": "France",
    "нідерланд*": "Netherlands",
    "голланд*": "Netherlands",
    "чехі*": "Czechia",
    "чехи*": "Czechia",
    "австрі*": "Austria",
    "австри*": "Austria",
    "швейцарі*": "Switzerland",
    "великобритані*": "United Kingdom",
    "румуні*": "Romania",
    "румыни*": "Romania",
    "бельгі*": "Belgium",
    "сша": "United States",
}
# Not "англі*": that stem is also "англійською", the language, and a brief that
# asks for English speakers is not a brief about Britain.

LEAD_COUNT = re.compile(
    r"(\d{1,4})\s*(?:лід|лид|lead|кандидат|candidate|людей|люд|осіб|особ|контакт|профіл|профил)",
    re.IGNORECASE,
)


class RuleBriefParser:
    """
    The no-model stand-in. Recognises what can be recognised without judgement
    and leaves everything else empty for the review screen to ask about.
    """

    name = "rules"

    async def parse(self, text: str, locale: str) -> ParsedBrief:
        brief = text.strip()[:MAX_BRIEF]
        lowered = brief.casefold()
        words = re.findall(r"[\w'’]+", lowered)

        languages = [
            code for code, stems in LANGUAGE_STEMS.items() if any(stem in lowered for stem in stems)
        ]
        # "українською" names a language, not Ukraine; "італійська" is not Italy.
        language_words = {
            word
            for word in words
            if any(stem in word for stems in LANGUAGE_STEMS.values() for stem in stems)
        }
        country = self._country(lowered, [word for word in words if word not in language_words])

        # The spelling the client used, and the brand's Latin name: the two reach
        # different people (`фармасі` and `farmasi` are different queries).
        brands: list[str] = []
        for canonical, spellings in KNOWN_BRANDS.items():
            found = [spelling for spelling in spellings if spelling in lowered]
            if found:
                brands.extend([*found, canonical])

        count = LEAD_COUNT.search(brief)
        code = next((code for code, name in COUNTRIES.items() if name == country), "")
        raw = {
            "country": code,
            "languages": languages,
            "brands": brands,
            "target_leads": int(count.group(1)) if count else 0,
        }
        return ParsedBrief(
            name=_fallback_name(brief), criteria=build_criteria(raw, brief), parser=self.name
        )

    @staticmethod
    def _country(lowered: str, words: list[str]) -> str | None:
        known = set(COUNTRIES.values())
        for key, country in {**COUNTRY_NAMES, **EXTRA_COUNTRY_STEMS}.items():
            if country not in known:
                continue
            if key.endswith("*"):
                if any(word.startswith(key[:-1]) for word in words):
                    return country
            elif re.search(rf"\b{re.escape(key)}\b", lowered):
                return country
        return None


class ResilientBriefParser:
    """
    The model, and the rules when the model is not there to answer.

    A brief that cannot be read by the model is still worth reading by rules: the
    client gets a review screen with what could be recognised and questions for
    the rest, instead of an error and a blank page.
    """

    def __init__(self, primary: BriefParser | None, fallback: BriefParser | None = None) -> None:
        self._primary = primary
        self._fallback = fallback or RuleBriefParser()
        self.name = primary.name if primary else self._fallback.name

    async def parse(self, text: str, locale: str) -> ParsedBrief:
        if self._primary is not None:
            try:
                return await self._primary.parse(text, locale)
            except ProviderError as error:
                log.warning("brief_parser_fell_back", extra={"error": str(error)})
        return await self._fallback.parse(text, locale)
