"""
Is this the name of a person?

The single most expensive mistake in lead discovery is a lead that is not a human:
somebody tries to contact a shop. Both extractors need the same bar — the snippet
one reads a search result title, the page one reads whatever the page claims — so
the vocabulary and the two checks live here rather than in either of them.

Nothing in this file is clever. It is a deliberately conservative filter: a missed
person costs one lead, an invented one costs the user's credibility (spec §32, §34).
"""

import re
import unicodedata

#: Words that mean the text is not a person, whatever else it looks like.
NOT_A_PERSON = {
    "about",
    "academy",
    "agency",
    "blog",
    "boutique",
    "careers",
    "clinic",
    "company",
    "contact",
    "products",
    "profiles",
    "shop",
    "store",
    "team",
    "gmbh",
    "ltd",
    "llc",
    "inc",
    "srl",
    "official",
    "login",
    "sign",
    "photos",
    "videos",
    "instagram",
    "facebook",
    "linkedin",
    "threads",
}

#: A brand's own account is the most common false positive in a search for people:
#: it ranks high, its title reads like a name and its handle gives it away.
#: Localised, because the account is in the country being searched.
BRAND_MARKERS = {
    "official",
    "oficial",
    "oficialna",
    "oficjalny",
    "offiziell",
    "ufficiale",
    "officiel",
    "brand",
    "tienda",
    "negozio",
    "sklep",
    "loja",
    "магазин",
    "cosmetics",
    "cosmetica",
    "cosmética",
}

#: Lowercase in the middle of a name is normal: "Ana de la Cruz", "Jan van Dijk".
PARTICLES = {"de", "del", "della", "di", "da", "dos", "la", "le", "van", "von", "der", "den", "bin"}


#: Pictographs and marks that decorate a name without being part of it.
_DECORATION = {"So", "Sk", "Mn", "Me", "Cs"}


def clean(value: str) -> str:
    """
    The text with invisible formatting removed and decorations trimmed off the ends.

    LinkedIn titles arrive as "‏Piotr Orlik‏ - …" (right-to-left marks around the
    name) and "🐍 Dawid Kosinski - …": both read as no name at all, and six Python
    developers were refused as "not a person" in one run.
    """
    text = "".join(ch for ch in value or "" if unicodedata.category(ch) != "Cf")
    text = re.sub(r"\s+", " ", text).strip(" \t\n\r-–—|·•,")
    start, end = 0, len(text)
    while start < end and _decoration(text[start]):
        start += 1
    while end > start and _decoration(text[end - 1]):
        end -= 1
    return text[start:end].strip(" \t\n\r-–—|·•,")


def _decoration(character: str) -> bool:
    return character == " " or unicodedata.category(character) in _DECORATION


def commercial(text: str) -> bool:
    """A name or handle belonging to a business rather than to a person."""
    tokens = {token for token in re.split(r"[^\w]+", (text or "").lower()) if token}
    return bool(tokens & (NOT_A_PERSON | BRAND_MARKERS))


def looks_like_a_person(text: str) -> bool:
    """Two to four name-shaped words. Deliberately strict: a false name is a lead."""
    words = (text or "").split()
    if not 2 <= len(words) <= 4 or len(text) > 60:
        return False
    if commercial(text):
        return False
    if any(character.isdigit() for character in text):
        return False
    return all(word[0].isupper() or word.lower() in PARTICLES for word in words)


def plausible_name(text: str) -> bool:
    """The lighter check, for cases where something else already vouches for the name."""
    words = (text or "").split()
    if not words or len(words) > 5 or len(text) > 60:
        return False
    if commercial(text):
        return False
    return any(character.isalpha() for character in text)
