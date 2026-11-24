"""
The closed vocabularies a brief is parsed into.

Everything here is a *token*, not a label: the value stored in the criteria and
used by the query generator and the market mapping. What the client sees is the
frontend's translation of it (`domain.country.<code>`, `domain.language.<code>`,
`domain.industry.<key>`, `domain.businessType.<key>`), so the same search reads
in Ukrainian for a Ukrainian interface and still asks the same question.

The lists mirror the frontend's `lib/domain.ts`. A value outside them is dropped
rather than guessed at — the review screen then asks for it.
"""

#: ISO 3166 code → the country name the rest of the backend keys on
#: (`markets.COUNTRY_CODES`, `phrasebook.PLACE_IN_LANGUAGE`, the location filter).
COUNTRIES: dict[str, str] = {
    "UA": "Ukraine",
    "ES": "Spain",
    "PL": "Poland",
    "DE": "Germany",
    "IT": "Italy",
    "PT": "Portugal",
    "FR": "France",
    "NL": "Netherlands",
    "CZ": "Czechia",
    "AT": "Austria",
    "CH": "Switzerland",
    "GB": "United Kingdom",
    "RO": "Romania",
    "BE": "Belgium",
    "US": "United States",
    "CA": "Canada",
    "IE": "Ireland",
    "NO": "Norway",
    "LV": "Latvia",
    "IL": "Israel",
    "KZ": "Kazakhstan",
    "RU": "Russia",
    "BY": "Belarus",
}

#: ISO 639-1 code → the language name `markets.LANGUAGE_CODES` keys on.
LANGUAGES: dict[str, str] = {
    "uk": "Ukrainian",
    "ru": "Russian",
    "en": "English",
    "es": "Spanish",
    "pl": "Polish",
    "de": "German",
    "it": "Italian",
    "pt": "Portuguese",
    "fr": "French",
    "ro": "Romanian",
    "cs": "Czech",
    "nl": "Dutch",
}

#: Industry tokens. English because `phrasebook.TERMS_IN_LANGUAGE` translates
#: from English into each query language; shown translated, never as typed here.
INDUSTRIES: tuple[str, ...] = (
    "Beauty",
    "Cosmetics",
    "Skincare",
    "Perfume",
    "Wellness",
    "Supplements",
    "Hair",
    "Nails",
    "Household",
)

BUSINESS_TYPES: tuple[str, ...] = (
    "MLM",
    "Network marketing",
    "Direct sales",
    "Affiliate",
    "Franchise",
)

#: Network-marketing brands and the spellings their distributors use, so the rule
#: parser can recognise them without a model. Each spelling is a query of its own:
#: `farmasi` and `фармасі` reach different people.
KNOWN_BRANDS: dict[str, tuple[str, ...]] = {
    "Farmasi": ("farmasi", "фармасі", "фармаси"),
    "Jerelia": ("jerelia", "джерелія", "джерелия"),
    "Oriflame": ("oriflame", "оріфлейм", "орифлейм"),
    "Avon": ("avon", "ейвон", "эйвон"),
    "Faberlic": ("faberlic", "фаберлік", "фаберлик"),
    "Amway": ("amway", "амвей", "эмвей"),
    "Mary Kay": ("mary kay", "мері кей", "мэри кэй"),
    "Herbalife": ("herbalife", "гербалайф"),
    "Atomy": ("atomy", "атомі", "атоми"),
    "Greenway": ("greenway", "грінвей", "гринвей"),
    "Coral Club": ("coral club", "корал клаб"),
    "MIHI": ("mihi",),
    "LR Health": ("lr health", "lr health & beauty"),
    "Forever Living": ("forever living",),
    "doTERRA": ("doterra", "дотерра"),
    "NL International": ("nl international", "nl интернешнл", "енель"),
}
