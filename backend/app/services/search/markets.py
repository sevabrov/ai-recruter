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
#:
#: A key ending in `*` is a stem, because Slavic languages inflect the place they
#: are talking about: a bio saying "з України" or "живу в Києві" names the country
#: just as plainly as "Ukraine" does, and a country filter that only knew the
#: nominative would drop exactly the people it was asked to find.
COUNTRY_NAMES: dict[str, str] = {
    "austria": "Austria",
    "österreich": "Austria",
    "oesterreich": "Austria",
    "belgium": "Belgium",
    "croatia": "Croatia",
    "hrvatska": "Croatia",
    "czechia": "Czechia",
    "czech republic": "Czechia",
    "česko": "Czechia",
    "česká republika": "Czechia",
    "denmark": "Denmark",
    "finland": "Finland",
    "france": "France",
    "germany": "Germany",
    "deutschland": "Germany",
    "німеччин*": "Germany",
    "герман*": "Germany",
    "italy": "Italy",
    "italia": "Italy",
    "netherlands": "Netherlands",
    "nederland": "Netherlands",
    "norway": "Norway",
    "poland": "Poland",
    "polska": "Poland",
    "польщ*": "Poland",
    "польш*": "Poland",
    "portugal": "Portugal",
    "romania": "Romania",
    "românia": "Romania",
    "russia": "Russia",
    "россия": "Russia",
    "росси*": "Russia",
    "spain": "Spain",
    "españa": "Spain",
    "espana": "Spain",
    "испани*": "Spain",
    "іспані*": "Spain",
    "sweden": "Sweden",
    "switzerland": "Switzerland",
    "schweiz": "Switzerland",
    "ukraine": "Ukraine",
    "ukraina": "Ukraine",
    "україн*": "Ukraine",
    "украин*": "Ukraine",
    "united kingdom": "United Kingdom",
    "great britain": "United Kingdom",
    "united states": "United States",
}

#: Where a city is. A profile almost never writes the country down — it writes
#: "Zagreb", "Київ", "Barcelona" — so without this the country filter would read
#: "unknown" on the very profiles it is meant to keep. Capitals and the largest
#: cities only: this is evidence, not a gazetteer.
CITY_NAMES: dict[str, str] = {
    # Ukraine
    "київ*": "Ukraine",
    "киев*": "Ukraine",
    "kyiv": "Ukraine",
    "kiev": "Ukraine",
    "львів*": "Ukraine",
    "львов*": "Ukraine",
    "lviv": "Ukraine",
    "харків*": "Ukraine",
    "харьков*": "Ukraine",
    "kharkiv": "Ukraine",
    "одес*": "Ukraine",
    "odesa": "Ukraine",
    "odessa": "Ukraine",
    "дніпр*": "Ukraine",
    "днепр*": "Ukraine",
    "dnipro": "Ukraine",
    # Spain
    "madrid": "Spain",
    "barcelona": "Spain",
    "valencia": "Spain",
    "sevilla": "Spain",
    "málaga": "Spain",
    "malaga": "Spain",
    "bilbao": "Spain",
    # Germany / Austria / Switzerland
    "berlin": "Germany",
    "münchen": "Germany",
    "munich": "Germany",
    "hamburg": "Germany",
    "köln": "Germany",
    "frankfurt": "Germany",
    "düsseldorf": "Germany",
    "wien": "Austria",
    "vienna": "Austria",
    "graz": "Austria",
    "salzburg": "Austria",
    "zürich": "Switzerland",
    "zurich": "Switzerland",
    "genève": "Switzerland",
    "geneva": "Switzerland",
    "basel": "Switzerland",
    # Italy
    "roma": "Italy",
    "milano": "Italy",
    "milan": "Italy",
    "napoli": "Italy",
    "torino": "Italy",
    "firenze": "Italy",
    # Poland / Czechia
    "warszaw*": "Poland",
    "warsaw": "Poland",
    "kraków": "Poland",
    "krakow": "Poland",
    "wrocław": "Poland",
    "wroclaw": "Poland",
    "poznań": "Poland",
    "gdańsk": "Poland",
    "praha": "Czechia",
    "prague": "Czechia",
    "brno": "Czechia",
    # Portugal / France / Netherlands / UK
    "lisboa": "Portugal",
    "lisbon": "Portugal",
    "porto": "Portugal",
    "paris": "France",
    "lyon": "France",
    "marseille": "France",
    "amsterdam": "Netherlands",
    "rotterdam": "Netherlands",
    "utrecht": "Netherlands",
    "london": "United Kingdom",
    "manchester": "United Kingdom",
    "birmingham": "United Kingdom",
    # Countries whose companies keep turning up in beauty/MLM searches
    "zagreb": "Croatia",
    "bucurești": "Romania",
    "bucuresti": "Romania",
    "bucharest": "Romania",
    "москв*": "Russia",
    "moscow": "Russia",
}

#: Everything that names a place, for the two questions that need it: "which
#: country is this profile in?" and "is this name a person or an organisation?"
#: (`Orbico Beauty Croatia` is not a person).
PLACE_NAMES: dict[str, str] = {**COUNTRY_NAMES, **CITY_NAMES}


def country_code(country: str | None) -> str | None:
    return COUNTRY_CODES.get((country or "").strip().lower())


def language_code(language: str | None) -> str | None:
    return LANGUAGE_CODES.get((language or "").strip().lower())


def language_name(code: str | None) -> str | None:
    """`"es-ES"` and `"es"` both mean Spanish; an unknown tag returns None."""
    if not code:
        return None
    return LANGUAGE_NAMES.get(code.strip().lower().split("-")[0].split("_")[0])
