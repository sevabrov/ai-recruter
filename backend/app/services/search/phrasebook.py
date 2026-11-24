"""
How to ask for the same person in another language (spec §29).

A search for beauty-industry network marketers in Ukraine, written in English,
finds English pages about Ukraine: company directories, "Top 10 MLM companies in
the Ukraine", the Romanian representative of a global brand. The people the
client is looking for write about themselves in Ukrainian and Russian, and no
amount of filtering downstream can recover a candidate the query never reached.

So the language the user selected is not decoration on the results — it is part
of the question. This file holds the few dozen words needed to ask it:

* `PLACE_IN_LANGUAGE` — how the country is written by the people who live there,
  because "Україна" and "Ukraine" are two different queries to a search index;
* `TERMS_IN_LANGUAGE` — the handful of concepts the templates are built from.

Deliberately small and hand-checked. A missing translation is not an error: the
generator falls back to the user's own keywords, which is exactly what Phase 4
did for every language.
"""

import re

#: The concepts the query templates use, keyed by language code.
#:
#: "consultant" is the word a brand's rep puts in her own bio — measured on Brave
#: against Poland: `site:instagram.com Avon` returned twenty official Avon accounts
#: from twenty countries, `Avon konsultantka Polska` returned a page of Polish
#: consultants. "shop" and "beauty salon" are here because they are the exclusions
#: a brief most often asks for, and an exclusion in the wrong language excludes
#: nothing.
TERMS_IN_LANGUAGE: dict[str, dict[str, str]] = {
    "uk": {
        "network marketing": "мережевий маркетинг",
        "mlm": "млм",
        "consultant": "консультант",
        "beauty": "краса",
        "team leader": "лідер команди",
        "join my team": "запрошую в команду",
        "shop": "магазин",
        "beauty salon": "салон краси",
    },
    "ru": {
        "network marketing": "сетевой маркетинг",
        "mlm": "млм",
        "consultant": "консультант",
        "beauty": "красота",
        "team leader": "лидер команды",
        "join my team": "приглашаю в команду",
        "shop": "магазин",
        "beauty salon": "салон красоты",
    },
    "es": {
        "network marketing": "marketing multinivel",
        "mlm": "MLM",
        "consultant": "consultora",
        "beauty": "belleza",
        "team leader": "líder de equipo",
        "join my team": "únete a mi equipo",
        "shop": "tienda",
        "beauty salon": "salón de belleza",
    },
    "de": {
        "network marketing": "netzwerkmarketing",
        "mlm": "MLM",
        "consultant": "beraterin",
        "beauty": "beauty",
        "team leader": "teamleiterin",
        "join my team": "werde teil meines teams",
        "shop": "shop",
        "beauty salon": "kosmetikstudio",
    },
    "it": {
        "network marketing": "network marketing",
        "mlm": "MLM",
        "consultant": "consulente",
        "beauty": "bellezza",
        "team leader": "team leader",
        "join my team": "entra nel mio team",
        "shop": "negozio",
        "beauty salon": "salone di bellezza",
    },
    "pl": {
        "network marketing": "marketing sieciowy",
        "mlm": "MLM",
        "consultant": "konsultantka",
        "beauty": "uroda",
        "team leader": "liderka zespołu",
        "join my team": "dołącz do mojego zespołu",
        "shop": "sklep",
        "beauty salon": "salon kosmetyczny",
    },
    "pt": {
        "network marketing": "marketing de rede",
        "mlm": "MLM",
        "consultant": "consultora",
        "beauty": "beleza",
        "team leader": "líder de equipa",
        "join my team": "junta-te à minha equipa",
        "shop": "loja",
        "beauty salon": "salão de beleza",
    },
    "fr": {
        "network marketing": "marketing de réseau",
        "mlm": "MLM",
        "consultant": "conseillère",
        "beauty": "beauté",
        "team leader": "chef d'équipe",
        "join my team": "rejoins mon équipe",
        "shop": "boutique",
        "beauty salon": "salon de beauté",
    },
    "nl": {
        "network marketing": "netwerkmarketing",
        "mlm": "MLM",
        "consultant": "consultant",
        "beauty": "beauty",
        "team leader": "teamleider",
        "join my team": "sluit je aan bij mijn team",
        "shop": "winkel",
        "beauty salon": "schoonheidssalon",
    },
}

#: Other ways a brief writes a concept, beyond the translations above.
ALIASES: dict[str, str] = {
    "multi-level marketing": "mlm",
    "network-marketing": "network marketing",
    "мережевий бізнес": "network marketing",
    "сетевой бизнес": "network marketing",
}

#: How a country is written in a language, where it differs from English. Only
#: the pairs that matter: a language is only ever paired with a place its
#: speakers write about.
PLACE_IN_LANGUAGE: dict[tuple[str, str], str] = {
    ("uk", "ukraine"): "Україна",
    ("ru", "ukraine"): "Украина",
    ("ru", "russia"): "Россия",
    ("uk", "poland"): "Польща",
    ("ru", "poland"): "Польша",
    ("uk", "germany"): "Німеччина",
    ("ru", "germany"): "Германия",
    ("uk", "spain"): "Іспанія",
    ("ru", "spain"): "Испания",
    ("uk", "czechia"): "Чехія",
    ("ru", "czechia"): "Чехия",
    ("es", "spain"): "España",
    ("de", "germany"): "Deutschland",
    ("de", "austria"): "Österreich",
    ("de", "switzerland"): "Schweiz",
    ("it", "italy"): "Italia",
    ("pl", "poland"): "Polska",
    ("pt", "portugal"): "Portugal",
    ("nl", "netherlands"): "Nederland",
    ("fr", "france"): "France",
    # Where each language's diaspora lives (`models.search.LANGUAGE_COUNTRIES`).
    ("uk", "italy"): "Італія",
    ("uk", "united kingdom"): "Велика Британія",
    ("uk", "united states"): "США",
    ("uk", "canada"): "Канада",
    ("ru", "kazakhstan"): "Казахстан",
    ("ru", "belarus"): "Беларусь",
    ("ru", "israel"): "Израиль",
    ("ru", "united states"): "США",
    ("ru", "latvia"): "Латвия",
    ("ru", "italy"): "Италия",
    ("ru", "united kingdom"): "Великобритания",
    ("pl", "united kingdom"): "Wielka Brytania",
    ("pl", "germany"): "Niemcy",
    ("pl", "ireland"): "Irlandia",
    ("pl", "netherlands"): "Holandia",
    ("pl", "norway"): "Norwegia",
    ("pl", "united states"): "USA",
    ("es", "mexico"): "México",
    ("es", "united states"): "Estados Unidos",
    ("es", "argentina"): "Argentina",
    ("es", "colombia"): "Colombia",
    ("it", "switzerland"): "Svizzera",
    ("pt", "brazil"): "Brasil",
    ("fr", "belgium"): "Belgique",
    ("fr", "switzerland"): "Suisse",
    ("fr", "canada"): "Canada",
    ("nl", "belgium"): "België",
}

#: Cities, for the same reason. Only the ones a wizard user is likely to type.
CITY_IN_LANGUAGE: dict[tuple[str, str], str] = {
    ("uk", "kyiv"): "Київ",
    ("ru", "kyiv"): "Киев",
    ("uk", "kiev"): "Київ",
    ("ru", "kiev"): "Киев",
    ("uk", "lviv"): "Львів",
    ("ru", "lviv"): "Львов",
    ("uk", "kharkiv"): "Харків",
    ("ru", "kharkiv"): "Харьков",
    ("uk", "odesa"): "Одеса",
    ("ru", "odesa"): "Одесса",
    ("es", "seville"): "Sevilla",
    ("de", "munich"): "München",
    ("de", "vienna"): "Wien",
    ("it", "rome"): "Roma",
    ("pl", "warsaw"): "Warszawa",
    ("pl", "cracow"): "Kraków",
    ("pt", "lisbon"): "Lisboa",
    # The cities a search digs into once its country queries are spent (`CITIES`).
    ("pl", "krakow"): "Kraków",
    ("pl", "wroclaw"): "Wrocław",
    ("pl", "poznan"): "Poznań",
    ("pl", "gdansk"): "Gdańsk",
    ("uk", "warsaw"): "Варшава",
    ("uk", "krakow"): "Краків",
    ("uk", "wroclaw"): "Вроцлав",
    ("uk", "poznan"): "Познань",
    ("uk", "gdansk"): "Гданськ",
    ("ru", "warsaw"): "Варшава",
    ("ru", "krakow"): "Краков",
    ("ru", "wroclaw"): "Вроцлав",
    ("ru", "poznan"): "Познань",
    ("ru", "gdansk"): "Гданьск",
    ("uk", "dnipro"): "Дніпро",
    ("ru", "dnipro"): "Днепр",
    ("de", "berlin"): "Berlin",
    ("de", "hamburg"): "Hamburg",
    ("de", "cologne"): "Köln",
    ("uk", "berlin"): "Берлін",
    ("uk", "munich"): "Мюнхен",
    ("uk", "hamburg"): "Гамбург",
    ("uk", "cologne"): "Кельн",
    ("ru", "berlin"): "Берлин",
    ("ru", "munich"): "Мюнхен",
    ("ru", "hamburg"): "Гамбург",
    ("ru", "cologne"): "Кёльн",
    ("pl", "berlin"): "Berlin",
    ("pl", "munich"): "Monachium",
    ("pl", "hamburg"): "Hamburg",
    ("pl", "cologne"): "Kolonia",
    ("uk", "prague"): "Прага",
    ("uk", "brno"): "Брно",
    ("ru", "prague"): "Прага",
    ("ru", "brno"): "Брно",
    ("es", "madrid"): "Madrid",
    ("es", "barcelona"): "Barcelona",
    ("es", "valencia"): "Valencia",
    ("uk", "madrid"): "Мадрид",
    ("uk", "barcelona"): "Барселона",
    ("uk", "valencia"): "Валенсія",
    ("ru", "madrid"): "Мадрид",
    ("ru", "barcelona"): "Барселона",
    ("ru", "valencia"): "Валенсия",
    ("it", "milan"): "Milano",
    ("it", "naples"): "Napoli",
    ("uk", "rome"): "Рим",
    ("uk", "milan"): "Мілан",
    ("uk", "naples"): "Неаполь",
    ("ru", "rome"): "Рим",
    ("ru", "milan"): "Милан",
    ("ru", "naples"): "Неаполь",
    ("uk", "london"): "Лондон",
    ("uk", "manchester"): "Манчестер",
    ("uk", "birmingham"): "Бірмінгем",
    ("ru", "london"): "Лондон",
    ("ru", "manchester"): "Манчестер",
    ("ru", "birmingham"): "Бирмингем",
    ("pl", "london"): "Londyn",
    ("pl", "manchester"): "Manchester",
    ("pl", "birmingham"): "Birmingham",
    ("ru", "moscow"): "Москва",
    ("ru", "saint petersburg"): "Санкт-Петербург",
    ("ru", "novosibirsk"): "Новосибирск",
    ("ru", "yekaterinburg"): "Екатеринбург",
    ("ru", "almaty"): "Алматы",
    ("ru", "astana"): "Астана",
    ("ru", "minsk"): "Минск",
}

#: The largest cities of a country, by their English names: where a search digs
#: once the country itself has been asked. A query with the country found the
#: same twenty accounts in every language; "Avon konsultantka Wrocław" is a
#: different twenty.
CITIES: dict[str, tuple[str, ...]] = {
    "poland": ("Warsaw", "Krakow", "Wroclaw", "Poznan", "Gdansk"),
    "ukraine": ("Kyiv", "Lviv", "Kharkiv", "Odesa", "Dnipro"),
    "germany": ("Berlin", "Munich", "Hamburg", "Cologne"),
    "czechia": ("Prague", "Brno"),
    "spain": ("Madrid", "Barcelona", "Valencia"),
    "italy": ("Rome", "Milan", "Naples"),
    "united kingdom": ("London", "Manchester", "Birmingham"),
    "russia": ("Moscow", "Saint Petersburg", "Novosibirsk", "Yekaterinburg"),
    "kazakhstan": ("Almaty", "Astana"),
    "belarus": ("Minsk",),
}


def cities(language: str | None, country: str | None) -> list[str]:
    """
    The country's largest cities as `language` writes them; English names for the
    untagged pass. A city we cannot write in the language is left out.
    """
    names = CITIES.get((country or "").strip().lower(), ())
    if language is None:
        return list(names)
    return [written for name in names if (written := place(language, name))]


def term(language: str | None, concept: str) -> str | None:
    """The word for a concept in a language, or None when we do not know it."""
    if not language:
        return None
    return TERMS_IN_LANGUAGE.get(language, {}).get(concept)


def _tidy(text: str) -> str:
    """Single-spaced, with every apostrophe written the same way."""
    for mark in "’ʼ`´":
        text = text.replace(mark, "'")
    return " ".join(text.split())


def _normal(text: str) -> str:
    return _tidy(text).casefold()


def _concepts() -> dict[str, str]:
    """Every word the phrasebook knows, in any language, to the concept it names."""
    known: dict[str, str] = {}
    for terms in TERMS_IN_LANGUAGE.values():
        for concept, word in terms.items():
            known.setdefault(_normal(concept), concept)
            known.setdefault(_normal(word), concept)
    for alias, concept in ALIASES.items():
        known.setdefault(_normal(alias), concept)
    return known


_CONCEPT_OF = _concepts()
#: Longest first, so "beauty salon" is one match rather than "beauty" and a leftover.
_KNOWN_WORDS = re.compile(
    "|".join(
        rf"(?<!\w){re.escape(word)}(?!\w)" for word in sorted(_CONCEPT_OF, key=len, reverse=True)
    ),
    re.IGNORECASE,
)


def translate(language: str | None, phrase: str) -> str | None:
    """
    The client's phrase written in `language`, or None when we cannot write it.

    A brief is read in the language the client typed it in, so its keywords
    arrive as "мережевий маркетинг" even when the search is for Poland. Sent as
    they are with a Polish query, `"мережевий маркетинг" Polska` came back empty
    — nine of a run's eighteen template queries returned nothing that way —
    while `"marketing sieciowy" Polska` returned eleven people.

    The phrase is recognised in whichever language it was written: as a whole
    ("млм" → "MLM"), or word by word when what is left over is a name
    ("консультант Avon" → "konsultantka Avon"). A leftover common word is not
    translated around: "beauty blogger" would become "uroda blogger", two
    languages in one phrase, which is a question nobody asks.
    """
    if not language or language not in TERMS_IN_LANGUAGE:
        return None
    text = _tidy(phrase)
    if not text:
        return None
    if (whole := _CONCEPT_OF.get(text.casefold())) is not None:
        return term(language, whole)

    def written(word: str) -> str | None:
        return term(language, _CONCEPT_OF.get(word.casefold(), ""))

    found = _KNOWN_WORDS.findall(text)
    leftovers = _KNOWN_WORDS.sub(" ", text).split()
    if not found or not all(_is_a_name(word) for word in leftovers):
        return None
    if any(written(word) is None for word in found):
        return None
    # Only the known words are replaced, so a name keeps the client's spelling.
    return _KNOWN_WORDS.sub(lambda match: written(match.group(0)) or match.group(0), text)


def _is_a_name(word: str) -> bool:
    """A brand or a place: capitalised, or no letters at all ("&", "24/7")."""
    letters = [char for char in word if char.isalpha()]
    return not letters or letters[0].isupper()


def place(language: str | None, name: str | None) -> str | None:
    """
    How this language writes a place. Returns None — not the English name — when
    there is no translation, so the caller can decide whether an untranslated
    query is worth firing at all.
    """
    if not language or not name:
        return None
    key = name.strip().lower()
    return PLACE_IN_LANGUAGE.get((language, key)) or CITY_IN_LANGUAGE.get((language, key))
