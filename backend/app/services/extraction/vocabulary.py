"""
The term lists behind keyword-level signal sightings.

This module is a stand-in for reading, and it is deliberately kept in one file so
Phase 6 can delete it in one commit. It exists because Phase 4 turns on real web
search: a search result carries a real title and description, and refusing to read
anything from them would mean a live search finds real people and reports none.

What it does *not* do is judge. It reports "this word occurs, here is the sentence
it occurs in", which is a sighting; whether that makes someone a match is the
signal detector's and the scoring service's business (spec §36–37).

Coverage is English plus the main languages of the countries the wizard offers.
A term list cannot do irony, negation or context — which is the honest argument
for the LLM detector, not against this file.
"""

import re

from app.models.common import SignalType
from app.services.search.markets import COUNTRY_NAMES

#: Signals that can be sighted in text at all. `location` comes from `find_country`,
#: `activity` and `personalBrand` need structure (dates, follower counts) as well.
SIGNAL_TERMS: dict[SignalType, tuple[str, ...]] = {
    SignalType.MLM: (
        "mlm",
        "network marketing",
        "networkmarketing",
        "netzwerkmarketing",
        "multi-level",
        "multilevel",
        "direct sales",
        "direct selling",
        "venta directa",
        "vendita diretta",
        "marketing de red",
        "sprzedaż bezpośrednia",
        "сетевой маркетинг",
        "distributor",
        "distribuidor",
        "distribuidora",
        "distributore",
        "dystrybutor",
        "vertriebspartner",
        "дистрибьютор",
        "independent consultant",
        "consultora independiente",
        "downline",
        "upline",
    ),
    SignalType.BEAUTY: (
        "beauty",
        "belleza",
        "bellezza",
        "beauté",
        "uroda",
        "красота",
        "cosmetic",
        "cosmetics",
        "cosmética",
        "cosmetica",
        "kosmetik",
        "kosmetyk",
        "косметик",
        "skincare",
        "skin care",
        "cuidado de la piel",
        "pflege",
        "makeup",
        "make-up",
        "maquillaje",
        "esthetician",
        "estética",
        "kosmetolog",
        "hairstylist",
        "perfume",
    ),
    SignalType.RECRUITING: (
        "recruiting",
        "recruitment",
        "recruit",
        "hiring",
        "join my team",
        "join our team",
        "join the team",
        "únete a mi equipo",
        "unete a mi equipo",
        "buscamos",
        "wir suchen",
        "cerchiamo",
        "szukamy",
        "team building",
        "build your team",
        "collaborators",
        "colaboradores",
        "ищу партнеров",
        "приглашаю в команду",
    ),
    SignalType.LEADERSHIP: (
        "leader",
        "líder",
        "lider",
        "leiter",
        "leiterin",
        "founder",
        "fundador",
        "fundadora",
        "gründerin",
        "gründer",
        "co-founder",
        "ceo",
        "director",
        "directora",
        "direttrice",
        "head of",
        "team lead",
        "manager",
        "mentor",
        "mentora",
        "coach",
        "наставник",
        "основатель",
    ),
    SignalType.PERSONAL_BRAND: (
        "linktr.ee",
        "beacons.ai",
        "link in bio",
        "content creator",
        "influencer",
        "brand ambassador",
        "embajadora",
        "podcast",
        "youtube.com",
        "blogger",
        "bloguera",
    ),
}

#: A page that says it was updated within this window counts as active.
ACTIVE_WITHIN_DAYS = 120

#: Below this, a follower count says nothing about a personal brand.
BRAND_FOLLOWERS = 2_000

_PATTERNS: dict[SignalType, list[tuple[str, re.Pattern[str]]]] = {
    signal: [
        (term, re.compile(rf"(?<!\w){re.escape(term)}(?!\w)", re.IGNORECASE)) for term in terms
    ]
    for signal, terms in SIGNAL_TERMS.items()
}

_COUNTRIES: list[tuple[str, re.Pattern[str]]] = [
    (name, re.compile(rf"(?<!\w){re.escape(spelling)}(?!\w)", re.IGNORECASE))
    for spelling, name in COUNTRY_NAMES.items()
]


def find_terms(text: str) -> dict[SignalType, list[str]]:
    """Which vocabulary terms occur in `text`, grouped by the signal they hint at."""
    if not text:
        return {}
    found: dict[SignalType, list[str]] = {}
    for signal, patterns in _PATTERNS.items():
        hits = [term for term, pattern in patterns if pattern.search(text)]
        if hits:
            found[signal] = hits
    return found


def find_country(text: str) -> tuple[str, str] | None:
    """
    The first country named in the text, as `(stored name, the words found)` —
    "España" in a bio is stored as Spain but quoted back as written.
    """
    if not text:
        return None
    best: tuple[int, str, str] | None = None
    for name, pattern in _COUNTRIES:
        match = pattern.search(text)
        if match and (best is None or match.start() < best[0]):
            best = (match.start(), name, match.group(0))
    return (best[1], best[2]) if best else None


def quote(text: str, term: str, width: int = 180) -> str:
    """
    The sentence-sized window around a term, so evidence is something the user can
    read and check rather than the word on its own (spec §16).
    """
    lowered = text.lower()
    position = lowered.find(term.lower())
    if position < 0:
        return text[:width].strip()

    start = max(0, position - width // 3)
    end = min(len(text), position + len(term) + 2 * width // 3)
    # Do not start or end mid-word.
    if start > 0 and (space := text.find(" ", start)) != -1 and space < position:
        start = space + 1
    if end < len(text) and (space := text.rfind(" ", position, end)) > position:
        end = space

    snippet = text[start:end].strip()
    return f"{'…' if start > 0 else ''}{snippet}{'…' if end < len(text) else ''}"
