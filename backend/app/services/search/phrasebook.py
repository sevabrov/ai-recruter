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

#: The concepts the query templates use, keyed by language code.
TERMS_IN_LANGUAGE: dict[str, dict[str, str]] = {
    "uk": {
        "network marketing": "мережевий маркетинг",
        "distributor": "дистриб'ютор",
        "beauty": "краса",
        "team leader": "лідер команди",
        "join my team": "запрошую в команду",
    },
    "ru": {
        "network marketing": "сетевой маркетинг",
        "distributor": "дистрибьютор",
        "beauty": "красота",
        "team leader": "лидер команды",
        "join my team": "приглашаю в команду",
    },
    "es": {
        "network marketing": "marketing multinivel",
        "distributor": "distribuidora",
        "beauty": "belleza",
        "team leader": "líder de equipo",
        "join my team": "únete a mi equipo",
    },
    "de": {
        "network marketing": "netzwerkmarketing",
        "distributor": "vertriebspartnerin",
        "beauty": "beauty",
        "team leader": "teamleiterin",
        "join my team": "werde teil meines teams",
    },
    "it": {
        "network marketing": "network marketing",
        "distributor": "distributrice",
        "beauty": "bellezza",
        "team leader": "team leader",
        "join my team": "entra nel mio team",
    },
    "pl": {
        "network marketing": "marketing sieciowy",
        "distributor": "dystrybutorka",
        "beauty": "uroda",
        "team leader": "liderka zespołu",
        "join my team": "dołącz do mojego zespołu",
    },
    "pt": {
        "network marketing": "marketing de rede",
        "distributor": "distribuidora",
        "beauty": "beleza",
        "team leader": "líder de equipa",
        "join my team": "junta-te à minha equipa",
    },
    "fr": {
        "network marketing": "marketing de réseau",
        "distributor": "distributrice",
        "beauty": "beauté",
        "team leader": "chef d'équipe",
        "join my team": "rejoins mon équipe",
    },
    "nl": {
        "network marketing": "netwerkmarketing",
        "distributor": "distributeur",
        "beauty": "beauty",
        "team leader": "teamleider",
        "join my team": "sluit je aan bij mijn team",
    },
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
}


def term(language: str | None, concept: str) -> str | None:
    """The word for a concept in a language, or None when we do not know it."""
    if not language:
        return None
    return TERMS_IN_LANGUAGE.get(language, {}).get(concept)


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
