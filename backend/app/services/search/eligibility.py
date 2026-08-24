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
one can be switched off per search (`requireLocation`, `requireLanguage`) —
because the honest cost of a hard filter is the candidate whose bio simply never
mentions where they live, and only the person running the search can decide
whether they would rather see those or not.

Every refusal carries the sentence that explains it. A search that returns four
leads instead of forty has to be able to say why, or the client is left guessing
whether the tool is strict or broken.
"""

from dataclasses import dataclass
from enum import StrEnum

from app.models.profile import ExtractedProfile
from app.models.search import SearchCriteria
from app.services.extraction import personhood


class Refusal(StrEnum):
    """Why a candidate did not become a lead. Counted, so the run can explain itself."""

    NOT_A_PERSON = "not_a_person"
    WRONG_COUNTRY = "wrong_country"
    WRONG_LANGUAGE = "wrong_language"
    MISSING_SIGNALS = "missing_signals"


@dataclass(frozen=True)
class Eligibility:
    admitted: bool
    refusal: Refusal | None = None
    detail: str = ""


ADMITTED = Eligibility(True)


def admit(profile: ExtractedProfile, criteria: SearchCriteria) -> Eligibility:
    """Whether this profile may become a lead, and if not, the reason in words."""
    verdict = personhood.assess(profile)
    if not verdict.is_person:
        return Eligibility(False, Refusal.NOT_A_PERSON, verdict.detail)

    country = (criteria.location.country or "").strip()
    if country and criteria.require_location:
        found = (profile.location.country or "").strip()
        if not found:
            return Eligibility(
                False,
                Refusal.WRONG_COUNTRY,
                f"Nothing on this profile places the person in {country}.",
            )
        if found.casefold() != country.casefold():
            return Eligibility(
                False,
                Refusal.WRONG_COUNTRY,
                f"This profile is in {found}, not {country}.",
            )

    wanted = [language.strip() for language in criteria.languages if language.strip()]
    if wanted and criteria.require_language:
        spoken = {language.casefold() for language in profile.languages}
        if not spoken:
            return Eligibility(
                False,
                Refusal.WRONG_LANGUAGE,
                "This profile gives no sign of which language the person publishes in.",
            )
        if not spoken & {language.casefold() for language in wanted}:
            return Eligibility(
                False,
                Refusal.WRONG_LANGUAGE,
                f"This profile publishes in {', '.join(sorted(profile.languages))}, "
                f"not in {' / '.join(wanted)}.",
            )

    return ADMITTED
