"""
Reading a search result (Phase 4's stand-in for reading a page).

The titles and descriptions below are the shapes the platforms actually publish.
Two properties matter more than any single field: a page that is not a person must
not become a lead, and nothing may be claimed that the result did not say.
"""

from datetime import UTC, datetime, timedelta

import pytest

from app.models.common import Platform, SignalType
from app.models.search import SearchCriteria
from app.models.source import DiscoveredUrl, UrlKind
from app.services.extraction.signal_detector import FixtureSignalDetector
from app.services.scraping.snippet_extractor import MAX_CONFIDENCE, SnippetProfileExtractor

INSTAGRAM = DiscoveredUrl(
    url="https://www.instagram.com/anna.beauty/",
    canonical_url="https://instagram.com/anna.beauty",
    platform=Platform.INSTAGRAM,
    kind=UrlKind.CANDIDATE,
    title="Anna López (@anna.beauty) • Instagram photos and videos",
    snippet=(
        "12.5K Followers, 812 Following, 341 Posts — Anna López (@anna.beauty): "
        "network marketing en el sector de la belleza. Líder de equipo en España. "
        "Únete a mi equipo · anna@example.com"
    ),
    query="site:instagram.com MIHI Spain",
    provider="brave",
    language="es",
)

LINKEDIN = DiscoveredUrl(
    url="https://www.linkedin.com/in/elena-ruiz-1234",
    canonical_url="https://linkedin.com/in/elena-ruiz-1234",
    platform=Platform.LINKEDIN,
    kind=UrlKind.CANDIDATE,
    title="Elena Ruiz - Team Leader - MIHI Iberia | LinkedIn",
    snippet="Distributor and team leader in cosmetics. Madrid, Spain · 500+ connections",
    query="site:linkedin.com/in MIHI Spain",
    provider="brave",
)


def discovered(**overrides) -> DiscoveredUrl:
    return INSTAGRAM.model_copy(update=overrides)


def signal(profile, kind: SignalType):
    return next(observation for observation in profile.observations if observation.type is kind)


# ------------------------------------------------------------------- identities


async def test_an_instagram_profile_yields_a_person_a_handle_and_an_audience():
    profile = await SnippetProfileExtractor().extract(INSTAGRAM)

    assert profile is not None
    assert profile.name == "Anna López"
    assert profile.platforms[0].handle == "@anna.beauty"
    assert profile.platforms[0].followers == 12_500
    assert profile.languages == ["Spanish"]  # the index's own language tag
    assert profile.contacts.email == "anna@example.com"
    assert profile.extractor == "snippet"
    # The evidence trail points at the real page, not at a fixture.
    assert profile.sources[0].url == "https://www.instagram.com/anna.beauty/"


async def test_a_linkedin_title_carries_the_headline_and_the_employer():
    profile = await SnippetProfileExtractor().extract(LINKEDIN)

    assert profile is not None
    assert profile.name == "Elena Ruiz"
    assert profile.headline == "Team Leader"
    assert profile.company == "MIHI Iberia"
    assert profile.platforms[0].handle == "@elena-ruiz-1234"


async def test_a_facebook_title_is_just_a_name():
    profile = await SnippetProfileExtractor().extract(
        discovered(
            url="https://www.facebook.com/marta.kowalska",
            canonical_url="https://facebook.com/marta.kowalska",
            platform=Platform.FACEBOOK,
            title="Marta Kowalska | Facebook",
            snippet="Marta Kowalska is on Facebook. Dystrybutor kosmetyków, Polska.",
        )
    )

    assert profile is not None and profile.name == "Marta Kowalska"


async def test_a_personal_site_is_a_lead_and_counts_as_a_place_of_their_own():
    profile = await SnippetProfileExtractor().extract(
        discovered(
            url="https://giuliabianchi.it/about",
            canonical_url="https://giuliabianchi.it/about",
            platform=Platform.WEBSITE,
            kind=UrlKind.UNKNOWN,
            title="Giulia Bianchi — Network marketing coach in Italia",
            snippet="Sono Giulia, distributore e mentor nel settore bellezza.",
            language="it",
        )
    )

    assert profile is not None
    assert profile.name == "Giulia Bianchi"
    assert profile.contacts.website == "https://giuliabianchi.it/about"
    assert signal(profile, SignalType.PERSONAL_BRAND).detected is True


@pytest.mark.parametrize(
    ("title", "snippet"),
    [
        ("Shop MIHI Cosmetics Online | Free shipping", "Buy beauty products"),
        ("Beauty & network marketing blog", "Ten tips for distributors"),
        ("Login | MIHI partner portal", "Sign in to continue"),
        ("anna.beauty • Instagram", "No display name in this title"),
    ],
)
async def test_a_page_that_is_not_a_person_does_not_become_a_lead(title, snippet):
    """A false name is a lead someone will try to contact (spec §32, §34)."""
    profile = await SnippetProfileExtractor().extract(
        discovered(
            platform=Platform.WEBSITE,
            kind=UrlKind.UNKNOWN,
            title=title,
            snippet=snippet,
        )
    )

    assert profile is None


async def test_a_url_the_discovery_stage_rejected_is_never_extracted():
    assert await SnippetProfileExtractor().extract(discovered(kind=UrlKind.COMPANY)) is None


@pytest.mark.parametrize(
    ("title", "snippet"),
    [
        (
            "MIHI España (@mihi.oficial) • Instagram photos and videos",
            "44,000 Followers — cosmética y network marketing. Tienda oficial.",
        ),
        (
            "MIHI Cosmetics (@mihi.cosmetics) • Instagram",
            "Beauty brand. Distribuidores en toda España.",
        ),
    ],
)
async def test_a_brands_own_account_is_not_a_candidate(title, snippet):
    """
    The single most common false positive when searching for people: the brand's
    account outranks everyone, and its title reads exactly like a name. The handle
    is what gives it away.
    """
    assert await SnippetProfileExtractor().extract(discovered(title=title, snippet=snippet)) is None


# ------------------------------------------------------------------ observations


async def test_what_the_result_says_is_recorded_with_the_words_it_said_it_in():
    profile = await SnippetProfileExtractor().extract(INSTAGRAM)
    assert profile is not None

    mlm = signal(profile, SignalType.MLM)
    assert mlm.detected is True
    assert "network marketing" in (mlm.evidence or "")
    assert mlm.source_url == INSTAGRAM.url

    assert signal(profile, SignalType.BEAUTY).detected is True  # "belleza"
    assert signal(profile, SignalType.RECRUITING).detected is True  # "Únete a mi equipo"
    assert signal(profile, SignalType.LEADERSHIP).detected is True  # "Líder"
    assert profile.location.country == "Spain"  # "España"


async def test_a_signal_the_result_is_silent_about_is_reported_as_not_found():
    """ "Not detected" and "never checked" must not look the same (spec §34)."""
    profile = await SnippetProfileExtractor().extract(
        discovered(title="Jan Novak (@jan.novak) • Instagram photos", snippet="Prague. Runner.")
    )

    assert profile is not None
    assert {observation.type for observation in profile.observations} == set(SignalType)
    quiet = signal(profile, SignalType.MLM)
    assert quiet.detected is False
    assert quiet.confidence == 0
    assert quiet.evidence is None


async def test_nothing_read_from_a_snippet_is_ever_certain():
    profile = await SnippetProfileExtractor().extract(INSTAGRAM)

    assert profile is not None
    assert all(observation.confidence <= MAX_CONFIDENCE for observation in profile.observations)


async def test_recency_comes_from_the_index_or_from_the_posting_count():
    fresh = await SnippetProfileExtractor().extract(
        discovered(page_age=datetime.now(UTC) - timedelta(days=3), age_label="3 days ago")
    )
    stale = await SnippetProfileExtractor().extract(
        discovered(
            page_age=datetime.now(UTC) - timedelta(days=900),
            snippet="Anna López (@anna.beauty): beauty, no numbers here",
        )
    )

    assert fresh is not None and stale is not None
    assert signal(fresh, SignalType.ACTIVITY).detected is True
    assert "3 days ago" in (signal(fresh, SignalType.ACTIVITY).evidence or "")
    assert signal(stale, SignalType.ACTIVITY).detected is False


async def test_the_posting_count_is_activity_when_the_index_gives_no_date():
    profile = await SnippetProfileExtractor().extract(INSTAGRAM)

    assert profile is not None
    assert "341 posts" in (signal(profile, SignalType.ACTIVITY).evidence or "").lower()


# ------------------------------------------------------- and on to the detector


async def test_the_detector_still_judges_geography_against_the_criteria():
    """
    The extractor reports where the page says the person is; whether that matches
    the search is the detector's call, and it is the same code either way.
    """
    profile = await SnippetProfileExtractor().extract(INSTAGRAM)
    assert profile is not None
    detector = FixtureSignalDetector()

    matching = await detector.detect(profile, SearchCriteria(location={"country": "Spain"}))
    mismatched = await detector.detect(profile, SearchCriteria(location={"country": "Germany"}))

    assert next(s for s in matching if s.type is SignalType.LOCATION).detected is True
    rejected = next(s for s in mismatched if s.type is SignalType.LOCATION)
    assert rejected.detected is False
    assert "Germany" in (rejected.evidence or "")
