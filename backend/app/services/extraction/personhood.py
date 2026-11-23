"""
Person or organisation? (spec §32, §34)

The product looks for people. A measured run returned four leads and three of
them were not human: a beauty distributor in Zagreb, a directory page titled
"Top 10 MLM Companies in the Ukraine", and a Facebook page for a magazine. Every
one of them passed the name check in `scraping/names.py`, because that check asks
whether a string is *shaped* like a name — and "Orbico Beauty Croatia", "Online
MLM Community" and "Network Marketing News" all are: two to four capitalised
words with no company suffix in sight.

Shape is not enough, so this module asks the three questions that separate the
two, and lets any one of them refuse:

* **the words.** An organisation usually says what it is — community, news,
  magazine, academy, studio, group — or carries a legal form (GmbH, ТОВ, s.r.o.).
* **the place.** People are not named after countries and cities. "Orbico Beauty
  Croatia" is a company however capitalised it is, and this rule is what catches
  the brand-plus-market naming that a keyword list never finishes covering.
* **the voice.** A company writes "we", "our clients", "founded in 1984", "the
  leading distributor in Europe". A person writes "I", "my team", "мій", "soy".
  This is the rule that survives a brand nobody has heard of.

Platform structure is evidence too, and it goes in both directions: `/in/<slug>`
on LinkedIn is a person by construction, while a Facebook page announces itself
with a like count and a category ("10 likes · Magazine").

The bar is deliberately asymmetric, and the same way round as everywhere else in
this codebase: a missed person costs one lead, an invented one costs the client's
credibility with somebody they then try to recruit.
"""

import re
from dataclasses import dataclass, field

from app.models.common import Platform
from app.models.profile import ExtractedProfile
from app.services.extraction.vocabulary import find_place, find_terms
from app.services.scraping.names import commercial, looks_like_a_person

#: What an organisation calls itself. Distinct from `names.NOT_A_PERSON`, which
#: is about a *handle or title* being commercial; these are the nouns an entity
#: uses for itself in the middle of an otherwise name-shaped title.
ORGANISATION_WORDS = {
    "academy",
    "agency",
    "association",
    "brand",
    "center",
    "centre",
    "channel",
    "club",
    "community",
    "company",
    "corporation",
    "distribution",
    "distributors",
    "federation",
    "forum",
    "foundation",
    "group",
    "holding",
    "hub",
    "institute",
    "international",
    "магазин",
    "magazine",
    "media",
    "network",
    "news",
    "official",
    "organization",
    "organisation",
    "portal",
    "press",
    "salon",
    "school",
    "solutions",
    "studio",
    "supply",
    "team",
    "wholesale",
    "worldwide",
    # The same nouns in the languages the wizard offers.
    "akademia",
    "akademie",
    "academia",
    "agencia",
    "agencja",
    "centrum",
    "centro",
    "comunidad",
    "compania",
    "empresa",
    "firma",
    "grupa",
    "grupo",
    "gruppo",
    "novosti",
    "новости",
    "новини",
    "спільнота",
    "сообщество",
    "компания",
    "компанія",
    "студия",
    "студія",
    "салон",
    "школа",
}

#: Legal forms. A name carrying one is not a person in any jurisdiction.
#:
#: Two-letter forms (SA, SL, AB, OY) are left out on purpose: they collide with
#: real surnames, and the cost of rejecting a person is higher here than the cost
#: of letting a company through to the checks below.
LEGAL_FORMS = {
    "gmbh",
    "doo",
    "inc",
    "kft",
    "llc",
    "ltd",
    "plc",
    "sarl",
    "srl",
    "sro",
    "ооо",
    "оао",
    "зао",
    "тов",
    "фоп",
}

#: How an organisation writes about itself. Matched against the summary, which is
#: the page's or the search result's own description of what it is.
CORPORATE_VOICE = (
    r"\bwe are\b",
    r"\bwe offer\b",
    r"\bwe provide\b",
    r"\bour (?:company|clients|customers|products|mission|team of)\b",
    r"\bthe (?:leading|largest|official)\b",
    r"\bfounded in \d{4}\b",
    r"\bestablished in \d{4}\b",
    r"\boperates in\b",
    r"\bpresent in \d+ countries\b",
    r"\bheadquarter",
    r"\bsomos\b",
    r"\bnuestra empresa\b",
    r"\bnuestros clientes\b",
    r"\bwir sind ein\b",
    r"\bunser unternehmen\b",
    r"\bnasza firma\b",
    r"\bмы — ?компания\b",
    r"\bнаша компания\b",
    r"\bнаші клієнти\b",
    r"\bнаша компанія\b",
    r"\bкомпани[яи] основана\b",
)

#: How a Facebook Page gives itself away in a search result: pages carry a like
#: count and a category, profiles carry neither.
#:
#: The like count alone is not proof of an organisation, though: the people this
#: product looks for — network-marketing leaders, coaches, mentors — very often
#: publish through a public Page under their own name ("Piotr Krenig …, 20,872
#: likes"). So a like count refuses only a Page whose name is not a person's; the
#: category refuses whatever the name.
FACEBOOK_LIKES = (r"\d[\d,. ]*\s*(?:likes|people like this|подписчик|вподоба)",)
FACEBOOK_PAGE = (
    r"·\s*(?:magazine|media|product/service|community|company|brand|shopping)",
    r"\.\s*(?:magazine|community|product/service)\b",
)

_ORGANISATION = {word.lower() for word in ORGANISATION_WORDS}
_LEGAL = {form.replace(".", "") for form in LEGAL_FORMS}
_CORPORATE = [re.compile(pattern, re.IGNORECASE) for pattern in CORPORATE_VOICE]
_FACEBOOK_PAGE = [re.compile(pattern, re.IGNORECASE) for pattern in FACEBOOK_PAGE]
_FACEBOOK_LIKES = [re.compile(pattern, re.IGNORECASE) for pattern in FACEBOOK_LIKES]
_WORDS = re.compile(r"[^\w]+", re.UNICODE)
#: A domain where a name should be. The article that got through was headlined by
#: its own publication: "PRAVO.UA".
_WEB_ADDRESS = re.compile(r"\w+\.(?:ua|ru|com|net|org|info|biz|io|co)\b", re.IGNORECASE)


@dataclass(frozen=True)
class Verdict:
    """Why a candidate is or is not a person, in words the client can read."""

    is_person: bool
    detail: str = ""
    #: The same refusal as a code and its facts, so the interface can say it in the
    #: client's language (`RejectedCandidate.detail_code`). `detail` stays English.
    code: str = ""
    params: dict[str, str] = field(default_factory=dict)


PERSON = Verdict(True)


def assess(profile: ExtractedProfile) -> Verdict:
    """Is the thing this profile describes a human being?"""
    name = (profile.name or "").strip()
    if not name:
        return Verdict(False, "No person is named on this page.", "no_name")

    if profile.platform is Platform.LINKEDIN and "/in/" in profile.canonical_url:
        # LinkedIn keeps people and companies on different paths, and only the
        # person path reaches this far (`url_tools.classify`). That is stronger
        # evidence than anything a title can offer, so it settles the question.
        return PERSON

    for token in _tokens(name):
        if token in _ORGANISATION:
            return _organisation_word(name, token)
        if token in _LEGAL:
            return _legal_form(name, token)

    topic = _topic(name)
    if topic:
        return Verdict(
            False,
            f"“{name}” is the subject being searched for, not a person.",
            "topic",
            {"name": name},
        )

    if _WEB_ADDRESS.search(name):
        return Verdict(
            False, f"“{name}” is a web address, not a person.", "web_address", {"name": name}
        )

    place = find_place(name)
    if place:
        return Verdict(
            False,
            f"“{name}” is named after a place ({place[1]}) — a brand, not a person.",
            "named_after_place",
            {"name": name, "place": place[1]},
        )

    if commercial(name):
        return Verdict(
            False, f"“{name}” reads as a business name.", "business_name", {"name": name}
        )

    summary = profile.summary or ""
    if profile.platform is Platform.FACEBOOK and _facebook_organisation_page(name, summary):
        return Verdict(
            False,
            f"“{name}” is a Facebook page, not somebody's profile.",
            "facebook_page",
            {"name": name},
        )

    corporate = _matches(_CORPORATE, summary)
    if corporate:
        return Verdict(
            False,
            f"“{name}” writes about itself as an organisation: “{corporate}”.",
            "corporate_voice",
            {"name": name, "quote": corporate},
        )

    return PERSON


def _organisation_word(name: str, token: str) -> Verdict:
    return Verdict(
        False,
        f"“{name}” names an organisation, not a person ({token}).",
        "organisation_word",
        {"name": name, "word": token},
    )


def _legal_form(name: str, token: str) -> Verdict:
    return Verdict(
        False,
        f"“{name}” carries a company form ({token.upper()}).",
        "legal_form",
        {"name": name, "form": token.upper()},
    )


def _facebook_organisation_page(name: str, summary: str) -> bool:
    """A Page that is an organisation's — by its category, or by likes and a non-name."""
    if _matches(_FACEBOOK_PAGE, summary):
        return True
    return bool(_matches(_FACEBOOK_LIKES, summary)) and not looks_like_a_person(name)


def before_reading(name: str, brands: list[str]) -> Verdict:
    """
    Is the search result alone enough to say this is not a person — before a credit
    is spent opening the page?

    `assess` answers after the page is read, and it lets LinkedIn's `/in/` path
    settle the question because the page is then there to contradict it. Asked of
    a search result, with money on the line, the bar is different, and narrower:
    only the *name* is looked at, and only for what no person's name carries.

    * **the brand being searched for, first.** People write "Anna Koval - Farmasi";
      the brand's own accounts are "Farmasi Bucuresti", "FARMASI TUNISIE", "Farmasi
      World". A measured run paid for ten such LinkedIn pages out of twenty-two, and
      one of them still came back as a lead.
    * **an organisation's own nouns or a legal form** — the same lists `assess` uses.

    The summary is deliberately not read: "we are hiring" in a real person's
    headline is exactly what `assess` was taught to forgive on LinkedIn, and a
    two-line snippet is too little to overrule that.
    """
    name = name.strip()
    if not name:
        return PERSON

    brand = _leading_brand(name, brands)
    if brand:
        return Verdict(
            False,
            f"“{name}” starts with {brand}, the brand being searched for — the "
            "brand's own account, not a person who works with it.",
            "searched_brand",
            {"name": name, "brand": brand},
        )

    for token in _tokens(name):
        if token in _ORGANISATION:
            return _organisation_word(name, token)
        if token in _LEGAL:
            return _legal_form(name, token)

    return PERSON


def _leading_brand(name: str, brands: list[str]) -> str:
    """The searched-for brand this name opens with, as the client typed it."""
    # Leading emoji, '#' and '@' are decoration, not part of the name.
    opening = re.sub(r"^[\W_]+", "", _fold(name))
    for brand in brands:
        folded = _fold(brand).strip()
        if len(folded) < 3 or not opening.startswith(folded):
            continue
        # A whole word, not a prefix: "Farmasi" is not the start of "Farmasiya".
        rest = opening[len(folded) :]
        if not rest or not rest[0].isalnum():
            return brand
    return ""


def _fold(text: str) -> str:
    """Case and apostrophes out of the way: J’erelia, J'erelia and j`erelia are one brand."""
    return re.sub(r"[’‘`´ʼ]", "'", text).casefold()


def _topic(name: str) -> bool:
    """
    Is the "name" simply what the search is about?

    A legal journal's article headed *СЕТЕВОЙ МАРКЕТИНГ* became a client's only
    lead: two capitalised words, no company noun, no place, and a Russian summary
    with no corporate voice in it. What gives it away is that the name is nothing
    but the vocabulary the search itself is built from — a subject line, not
    somebody who could be contacted.
    """
    words = _tokens(name)
    if not words:
        return False
    for terms in find_terms(name).values():
        for term in terms:
            words -= _tokens(term)
    return not words


def _tokens(text: str) -> set[str]:
    return {token for token in _WORDS.split(text.lower()) if token}


def _matches(patterns: list[re.Pattern[str]], text: str) -> str:
    """The phrase that matched, so the verdict can quote its own evidence."""
    for pattern in patterns:
        match = pattern.search(text or "")
        if match:
            return match.group(0).strip()
    return ""
