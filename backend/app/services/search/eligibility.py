"""
Who is allowed to become a lead (spec §32, §35, §37).

Until now every criterion was worth *points*: a profile in the wrong country
scored ten fewer and still arrived in the client's list. A run in August made the
problem concrete — a search for Ukraine returned a distributor in Croatia, a
representative in Romania and a Facebook magazine, all of them correctly scored
and none of them contactable. The client's words: they must all be only from the
country I chose, and the search must be for people only.

So three of the criteria stopped being weights and became gates:

* **person** — decided by `extraction/personhood.py`;
* **country** — the profile has to place itself in the country that was asked for;
* **language** — it has to publish in one of the languages that were asked for.

Each gate applies only when the client actually filled that field in, and each
one can be switched off per search (`requireLocation`, `requireLanguage`).

**A gate refuses a contradiction, not a silence.** The first version treated
"this person is in Romania" and "we could not tell" as the same answer, and a
search that asked for ten leads returned none: of 24 candidates refused, 19 went
on geography and exactly one of them was actually somewhere else. The rest were
Instagram profiles whose page would not open and whose two-line description named
no city — which is not evidence of the wrong country, it is no evidence.

So an unproven criterion passes, and pays for it in points: the signal stays
`detected: false`, so the lead scores lower and sorts below the confirmed ones.
`requireConfirmedLocation` / `requireConfirmedLanguage` restore the strict reading
for a client who would rather have five certain people than fifty likely ones.

Every refusal carries the sentence that explains it. A search that returns four
leads instead of forty has to be able to say why, or the client is left guessing
whether the tool is strict or broken.
"""

from dataclasses import dataclass, field
from enum import StrEnum

from app.models.profile import ExtractedProfile
from app.models.search import SearchCriteria
from app.services.extraction import personhood
from app.services.search.markets import iso_code, language_code


class Refusal(StrEnum):
    """Why a candidate did not become a lead. Counted, so the run can explain itself."""

    #: The reader failed on the address, so there was nothing to judge. Kept apart
    #: from `NOT_A_PERSON`, which the two shared until now: "we opened the page and
    #: there was no person on it" and "we never got the page" are different
    #: problems, and only one of them is about the candidate.
    UNREADABLE = "unreadable"
    NOT_A_PERSON = "not_a_person"
    WRONG_COUNTRY = "wrong_country"
    WRONG_LANGUAGE = "wrong_language"
    MISSING_SIGNALS = "missing_signals"


@dataclass(frozen=True)
class Eligibility:
    admitted: bool
    refusal: Refusal | None = None
    detail: str = ""
    #: The refusal as a code and its facts, for the interface's own language.
    code: str = ""
    params: dict[str, str] = field(default_factory=dict)


ADMITTED = Eligibility(True)


def admit(profile: ExtractedProfile, criteria: SearchCriteria) -> Eligibility:
    """Whether this profile may become a lead, and if not, the reason in words."""
    verdict = personhood.assess(profile)
    if not verdict.is_person:
        return Eligibility(
            False, Refusal.NOT_A_PERSON, verdict.detail, verdict.code, verdict.params
        )

    place = criteria.place_label()
    if criteria.allowed_countries() and criteria.require_location:
        found = (profile.location.country or "").strip()
        if criteria.in_allowed_place(found) is False:
            # The profile says somewhere else. That is a contradiction, and it is
            # refused whatever the settings say — it is the whole point of asking.
            return Eligibility(
                False,
                Refusal.WRONG_COUNTRY,
                f"This profile is in {found}, not {place}.",
                "wrong_country",
                {"found": country_param(found), "place": place_param(criteria)},
            )
        if not found and criteria.require_confirmed_location:
            return Eligibility(
                False,
                Refusal.WRONG_COUNTRY,
                f"Nothing on this profile confirms {place}, and this search asked "
                "for confirmed locations only.",
                "country_unconfirmed",
                {"place": place_param(criteria)},
            )

    wanted = [language.strip() for language in criteria.languages if language.strip()]
    if wanted and criteria.require_language:
        spoken = {language.casefold() for language in profile.languages}
        if spoken and not spoken & {language.casefold() for language in wanted}:
            return Eligibility(
                False,
                Refusal.WRONG_LANGUAGE,
                f"This profile publishes in {', '.join(sorted(profile.languages))}, "
                f"not in {' / '.join(wanted)}.",
                "wrong_language",
                {
                    "found": languages_param(sorted(profile.languages)),
                    "wanted": languages_param(wanted),
                },
            )
        if not spoken and criteria.require_confirmed_language:
            return Eligibility(
                False,
                Refusal.WRONG_LANGUAGE,
                "Nothing on this profile shows which language the person publishes "
                "in, and this search asked for confirmed languages only.",
                "language_unconfirmed",
            )

    return ADMITTED


def country_param(country: str | None) -> str:
    """A country as the interface can name it: its ISO code, else as written."""
    return iso_code(country) or (country or "")


def place_param(criteria: SearchCriteria) -> str:
    """The asked-for places, each as `country_param`, joined by "|"."""
    names = [criteria.location.country] if criteria.location.country else list(criteria.countries)
    places = [country_param(name) for name in names if name]
    if criteria.region:
        places.append(criteria.region.capitalize())
    return "|".join(places)


def languages_param(languages: list[str]) -> str:
    """Languages as ISO codes where known, joined by "|"."""
    return "|".join(language_code(name) or name for name in languages if name)
