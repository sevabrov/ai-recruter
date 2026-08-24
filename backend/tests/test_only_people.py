"""
Only people, and only where the client asked for them (spec §32, §35).

Every case in this file is taken from one real run. A search for beauty-industry
network marketers in Ukraine, in Russian and Ukrainian, returned four leads:

    Orbico Beauty Croatia     a distributor in Zagreb
    Online MLM Community      a listicle titled "Top 10 MLM Companies in the Ukraine"
    Gabriela Petrescu         a real person, representing Nu Skin — in Romania
    Network Marketing News    a Facebook page for a magazine, 10 likes

Three of the four are not people; the fourth is a person in the wrong country.
All four scored, because until now the country was worth ten points rather than
being a requirement. The client's answer was unambiguous: people only, and only
from the country and languages chosen.

So the tests are written from the refusals, and each one names the evidence that
does the refusing — the word, the place, the voice, the page marker. The last two
guard the other direction, which is the expensive one: a real person must not be
lost because a heuristic got clever.
"""

import pytest

from app.models.common import GeoLocation, Platform, SignalType
from app.models.profile import ExtractedProfile
from app.models.search import SearchCriteria
from app.services.extraction import personhood
from app.services.search.eligibility import Refusal, admit

pytestmark = pytest.mark.anyio


def profile(
    name: str,
    *,
    platform: Platform = Platform.WEBSITE,
    url: str = "https://example.com/",
    summary: str = "",
    country: str | None = None,
    languages: list[str] | None = None,
) -> ExtractedProfile:
    return ExtractedProfile(
        url=url,
        canonical_url=url,
        platform=platform,
        name=name,
        summary=summary,
        location=GeoLocation(country=country),
        languages=languages or [],
        extractor="snippet",
    )


def criteria(**overrides) -> SearchCriteria:
    return SearchCriteria.model_validate(
        {
            "keywords": ["network marketing"],
            "industry": ["Beauty"],
            "location": {"country": "Ukraine"},
            "languages": ["Russian", "Ukrainian"],
            "must_have": [SignalType.MLM.value],
            "sources": ["instagram_public"],
            **overrides,
        }
    )


# ------------------------------------------------------- the four that got through


def test_a_company_named_after_its_market_is_not_a_person():
    """`Orbico Beauty Croatia` — three capitalised words, and a place among them."""
    verdict = personhood.assess(
        profile(
            "Orbico Beauty Croatia",
            url="https://www.orbicobeauty.hr/en/",
            summary="Today we are the leading beauty distributor in Europe, in 19 countries.",
        )
    )

    assert not verdict.is_person
    assert "Croatia" in verdict.detail


def test_a_directory_calling_itself_a_community_is_not_a_person():
    verdict = personhood.assess(
        profile(
            "Online MLM Community",
            url="https://onlinemlmcommunity.com/mlm-companies-in-the-ukraine/",
            summary="Founded in 1984 in the United States, Nu Skin operates in Ukraine.",
        )
    )

    assert not verdict.is_person
    assert "community" in verdict.detail


def test_a_facebook_page_announces_itself_with_a_like_count():
    verdict = personhood.assess(
        profile(
            "Marta Beauty",
            platform=Platform.FACEBOOK,
            url="https://facebook.com/marta.beauty",
            summary="Marta Beauty. 10 likes. Magazine",
        )
    )

    assert not verdict.is_person
    assert "Facebook page" in verdict.detail


def test_a_person_in_the_wrong_country_is_refused_not_discounted():
    """
    Gabriela Petrescu is a real distributor. She is in Romania, and the search
    asked for Ukraine — which used to cost her ten points and let her through.
    """
    romanian = profile(
        "Gabriela Petrescu",
        platform=Platform.LINKEDIN,
        url="https://www.linkedin.com/in/gabrielapetrescu/",
        country="Romania",
        languages=["Russian"],
    )

    outcome = admit(romanian, criteria())

    assert not outcome.admitted
    assert outcome.refusal is Refusal.WRONG_COUNTRY
    assert "Romania" in outcome.detail and "Ukraine" in outcome.detail


# ------------------------------------------------------------------ the gates


def test_a_profile_that_never_says_where_it_is_does_not_pass_a_country_filter():
    """
    The honest cost of the filter, made explicit: "we could not tell" is a refusal,
    not a pass. It is per search (`requireLocation`) for exactly this reason.
    """
    nowhere = profile(
        "Marta Ruiz",
        platform=Platform.LINKEDIN,
        url="https://www.linkedin.com/in/marta-ruiz/",
        languages=["Ukrainian"],
    )

    assert admit(nowhere, criteria()).refusal is Refusal.WRONG_COUNTRY
    assert admit(nowhere, criteria(require_location=False)).admitted


def test_the_language_filter_asks_what_the_person_publishes_in():
    english_only = profile(
        "Marta Ruiz",
        platform=Platform.LINKEDIN,
        url="https://www.linkedin.com/in/marta-ruiz/",
        country="Ukraine",
        languages=["English"],
    )

    outcome = admit(english_only, criteria())

    assert outcome.refusal is Refusal.WRONG_LANGUAGE
    assert "English" in outcome.detail
    assert admit(english_only, criteria(require_language=False)).admitted


def test_a_filter_the_client_did_not_ask_for_does_not_apply():
    """A search with no country and no languages judges nobody on either."""
    anyone = profile(
        "Marta Ruiz",
        platform=Platform.LINKEDIN,
        url="https://www.linkedin.com/in/marta-ruiz/",
    )

    assert admit(anyone, criteria(location={}, languages=[])).admitted


# -------------------------------------------------- and the people who must survive


def test_a_person_on_linkedin_is_a_person_whatever_their_name_reads_like():
    """
    `/in/<slug>` is a person by construction — LinkedIn keeps companies on another
    path — so structure settles it before any wordlist gets an opinion. This is the
    rule that protects a real Ms. Nowak whose headline mentions her company.
    """
    verdict = personhood.assess(
        profile(
            "Marta Nowak",
            platform=Platform.LINKEDIN,
            url="https://www.linkedin.com/in/marta-nowak/",
            summary="We are hiring. Our company is the leading distributor in Poland.",
        )
    )

    assert verdict.is_person


def test_a_beauty_distributor_writing_in_the_first_person_is_a_person():
    ukrainian = profile(
        "Оксана Мельник",
        platform=Platform.INSTAGRAM,
        url="https://instagram.com/oksana.beauty",
        summary="Дистриб'ютор косметики, Київ. Запрошую в команду, разом до результату.",
        country="Ukraine",
        languages=["Ukrainian"],
    )

    assert personhood.assess(ukrainian).is_person
    assert admit(ukrainian, criteria()).admitted


def test_a_missing_name_is_the_first_refusal():
    assert not personhood.assess(profile("")).is_person
    assert admit(profile(""), criteria()).refusal is Refusal.NOT_A_PERSON
