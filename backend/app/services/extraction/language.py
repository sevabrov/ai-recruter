"""
Which language is this profile written in?

The search index tags a result with one language, and that tag is a fact worth
keeping — but it is the language of a *page*, decided by a crawler, and it is
routinely `en` for a bio written half in Ukrainian. Once the client asked for a
hard language filter, one crawler's opinion became the difference between a lead
and a discarded person, which is not a decision this file is willing to leave to
a single tag.

So the text gets a second opinion, from the two things text can be asked cheaply:

* **its script.** Cyrillic is not a language, but the letters that only exist in
  one of them are: `ї є і ґ` are Ukrainian, `ы э ъ ё` are Russian.
* **its function words.** Every language repeats a handful of them, and they are
  short, unambiguous and unlike each other across the languages the wizard offers.

What comes out is coarse and it is meant to be: the question asked upstream is
"does this person publish in a language the client can talk to?", not "what is
the ISO code of this sentence". Nothing here overrules the index tag — the two
are added together, because a person can perfectly well publish in both.
"""

import re

from app.services.search.markets import language_name

#: Letters that belong to exactly one of the two Cyrillic languages we care about.
UKRAINIAN_LETTERS = re.compile(r"[їієґЇІЄҐ]")
RUSSIAN_LETTERS = re.compile(r"[ыэъёЫЭЪЁ]")
CYRILLIC = re.compile(r"[Ѐ-ӿ]")

#: Function words, which is what a short bio has instead of grammar we can parse.
#: Two hits are required before a language is claimed, so one loan word ("beauty",
#: "coach", "team") never renames the profile.
STOPWORDS: dict[str, tuple[str, ...]] = {
    "uk": ("та", "що", "для", "які", "мене", "моя", "разом", "команда", "більше", "тут"),
    "ru": ("и", "что", "для", "меня", "моя", "вместе", "команда", "больше", "здесь", "как"),
    "en": ("the", "and", "with", "your", "for", "team", "join", "about", "our", "you"),
    "es": ("de", "que", "para", "con", "mi", "equipo", "tu", "más", "soy", "en"),
    "it": ("che", "per", "con", "mio", "squadra", "sono", "più", "della", "nel", "una"),
    "de": ("und", "mit", "für", "ich", "mein", "team", "auch", "eine", "das", "bei"),
    "pl": ("i", "że", "dla", "moja", "zespół", "jestem", "więcej", "tutaj", "oraz", "nie"),
    "pt": ("de", "que", "para", "com", "minha", "equipa", "sou", "mais", "aqui", "não"),
    "fr": ("et", "que", "pour", "avec", "mon", "équipe", "je", "plus", "ici", "une"),
    "nl": ("en", "van", "voor", "met", "mijn", "team", "ook", "hier", "niet", "een"),
}

MIN_HITS = 2

_PATTERNS: dict[str, list[re.Pattern[str]]] = {
    code: [re.compile(rf"(?<!\w){re.escape(word)}(?!\w)", re.IGNORECASE) for word in words]
    for code, words in STOPWORDS.items()
}


def detect_codes(text: str) -> list[str]:
    """The language codes the text itself supports, most confident first."""
    if not text or not text.strip():
        return []

    found: list[str] = []
    cyrillic = bool(CYRILLIC.search(text))
    if cyrillic:
        # Script first: it settles Ukrainian versus Russian, which function words
        # alone cannot, since the two share most of their short ones.
        if UKRAINIAN_LETTERS.search(text):
            found.append("uk")
        if RUSSIAN_LETTERS.search(text):
            found.append("ru")
        if not found:
            # Cyrillic with nothing distinctive in it. `і ї є ґ` are among the most
            # common letters in Ukrainian — "і" is the word "and" — so a whole bio
            # without one of them is itself evidence, and this is the reading that
            # is wrong less often.
            found.append("ru")

    scored = sorted(
        (
            (hits, code)
            for code, patterns in _PATTERNS.items()
            if (hits := sum(1 for pattern in patterns if pattern.search(text))) >= MIN_HITS
        ),
        reverse=True,
    )
    # One winner, and only if it wins outright. Spanish and Portuguese share half
    # their function words, so a tie is not two languages — it is this file being
    # unable to tell, and saying so beats putting "Portuguese" on a Spaniard.
    best = [code for hits, code in scored if hits == scored[0][0]] if scored else []
    if len(best) == 1 and best[0] not in found:
        found.append(best[0])
    return found


def detect(text: str) -> list[str]:
    """`detect_codes`, as the language names the rest of the product speaks."""
    return [name for code in detect_codes(text) if (name := language_name(code))]


def spoken(named: list[str | None], *texts: str | None) -> list[str]:
    """
    Every language the evidence supports, deduplicated, named ones first.

    `named` is what something already told us — the index's language tag, or a
    page that states its own — and `texts` is what the person actually wrote.
    Both are kept: a bio in Ukrainian on a page the crawler tagged English is one
    person publishing in two languages, not a contradiction to resolve.
    """
    languages: list[str] = []
    for language in named:
        if language and language not in languages:
            languages.append(language)
    for text in texts:
        for language in detect(text or ""):
            if language not in languages:
                languages.append(language)
    return languages
