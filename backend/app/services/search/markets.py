"""
Country and language codes for the search providers.

A generated query already carries the place as text ("… Spain"), which is a hint.
The provider's own market parameters are much stronger: they change which index is
searched, so `country=ES` surfaces Spanish profiles that a global search buries.

Only codes the provider documents are sent. Anything else resolves to `None` — a
worldwide search with the country still in the query text — because a rejected
parameter would fail the whole query, and a silently wrong market is worse than
no market at all. Czechia and Ukraine are the two countries the wizard offers that
Brave has no market for; they take that path on purpose.
"""

#: Brave's documented `country` values, keyed by the names the wizard produces.
COUNTRY_CODES: dict[str, str] = {
    "argentina": "AR",
    "australia": "AU",
    "austria": "AT",
    "belgium": "BE",
    "brazil": "BR",
    "canada": "CA",
    "chile": "CL",
    "china": "CN",
    "denmark": "DK",
    "finland": "FI",
    "france": "FR",
    "germany": "DE",
    "hong kong": "HK",
    "india": "IN",
    "indonesia": "ID",
    "italy": "IT",
    "japan": "JP",
    "korea": "KR",
    "south korea": "KR",
    "malaysia": "MY",
    "mexico": "MX",
    "netherlands": "NL",
    "new zealand": "NZ",
    "norway": "NO",
    "philippines": "PH",
    "poland": "PL",
    "portugal": "PT",
    "russia": "RU",
    "saudi arabia": "SA",
    "south africa": "ZA",
    "spain": "ES",
    "sweden": "SE",
    "switzerland": "CH",
    "taiwan": "TW",
    "turkey": "TR",
    "united kingdom": "GB",
    "great britain": "GB",
    "uk": "GB",
    "england": "GB",
    "united states": "US",
    "usa": "US",
    "us": "US",
}

#: Brave's `search_lang` values for the languages the wizard suggests.
LANGUAGE_CODES: dict[str, str] = {
    "bulgarian": "bg",
    "catalan": "ca",
    "croatian": "hr",
    "czech": "cs",
    "danish": "da",
    "dutch": "nl",
    "english": "en",
    "estonian": "et",
    "finnish": "fi",
    "french": "fr",
    "german": "de",
    "greek": "el",
    "hungarian": "hu",
    "italian": "it",
    "latvian": "lv",
    "lithuanian": "lt",
    "norwegian": "nb",
    "polish": "pl",
    "portuguese": "pt-pt",
    "romanian": "ro",
    "russian": "ru",
    "serbian": "sr",
    "slovak": "sk",
    "slovenian": "sl",
    "spanish": "es",
    "swedish": "sv",
    "turkish": "tr",
    "ukrainian": "uk",
}

#: The reverse map, for turning a result's language tag into something readable.
LANGUAGE_NAMES: dict[str, str] = {
    code.split("-")[0]: name.capitalize() for name, code in LANGUAGE_CODES.items()
}

#: How a country is spelled when it is written onto a profile. One spelling per
#: country: two spellings would split the country facet in the UI. The keys are
#: what we look for in a page's text, the values what gets stored.
COUNTRY_NAMES: dict[str, str] = {
    "austria": "Austria",
    "belgium": "Belgium",
    "czechia": "Czechia",
    "czech republic": "Czechia",
    "denmark": "Denmark",
    "finland": "Finland",
    "france": "France",
    "germany": "Germany",
    "deutschland": "Germany",
    "italy": "Italy",
    "italia": "Italy",
    "netherlands": "Netherlands",
    "norway": "Norway",
    "poland": "Poland",
    "polska": "Poland",
    "portugal": "Portugal",
    "russia": "Russia",
    "spain": "Spain",
    "españa": "Spain",
    "espana": "Spain",
    "sweden": "Sweden",
    "switzerland": "Switzerland",
    "ukraine": "Ukraine",
    "united kingdom": "United Kingdom",
    "great britain": "United Kingdom",
    "united states": "United States",
}


def country_code(country: str | None) -> str | None:
    return COUNTRY_CODES.get((country or "").strip().lower())


def language_code(language: str | None) -> str | None:
    return LANGUAGE_CODES.get((language or "").strip().lower())


def language_name(code: str | None) -> str | None:
    """`"es-ES"` and `"es"` both mean Spanish; an unknown tag returns None."""
    if not code:
        return None
    return LANGUAGE_NAMES.get(code.strip().lower().split("-")[0].split("_")[0])
