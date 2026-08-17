"""URL handling, deduplication and retries — the pure-code parts of the pipeline."""

import pytest

from app.core.retry import retry_async
from app.models.common import Platform
from app.models.lead import Lead, LeadContacts, LeadPlatform
from app.models.source import ProviderResult, UrlKind
from app.services.search.deduplicator import deduplicate
from app.services.search.query_generator import TemplateQueryGenerator
from app.services.search.url_tools import canonicalize, classify, detect_platform, discover

# ------------------------------------------------------------------ normalization


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("https://instagram.com/anna/", "https://instagram.com/anna"),
        ("https://www.instagram.com/anna/?utm_source=google", "https://instagram.com/anna"),
        ("https://m.instagram.com/anna//?igshid=abc", "https://instagram.com/anna"),
        ("https://WWW.Example.com/Team?fbclid=1", "https://example.com/Team"),
    ],
)
def test_canonicalize_collapses_the_same_page(raw, expected):
    assert canonicalize(raw) == expected


def test_the_spec_example_becomes_one_url():
    """Spec §31: `instagram.com/anna/` and the utm-tagged variant are one candidate."""
    assert canonicalize("instagram.com/anna/") == canonicalize(
        "instagram.com/anna/?utm_source=google"
    )


@pytest.mark.parametrize(
    ("url", "platform"),
    [
        ("https://instagram.com/anna", Platform.INSTAGRAM),
        ("https://linkedin.com/in/anna", Platform.LINKEDIN),
        ("https://facebook.com/anna", Platform.FACEBOOK),
        ("https://threads.net/@anna", Platform.THREADS),
        ("https://anna.es", Platform.WEBSITE),
        ("https://anna.es/blog/mlm", Platform.BLOG),
    ],
)
def test_platform_detection(url, platform):
    assert detect_platform(url) is platform


@pytest.mark.parametrize(
    ("url", "kind"),
    [
        ("https://instagram.com/anna", UrlKind.CANDIDATE),
        ("https://instagram.com/p/Cxyz", UrlKind.ARTICLE),
        ("https://linkedin.com/in/anna-kowalska", UrlKind.CANDIDATE),
        ("https://linkedin.com/company/mihi", UrlKind.COMPANY),
        ("https://shop.example.com/shop/lipstick", UrlKind.PRODUCT),
    ],
)
def test_candidate_discovery_classifies_urls(url, kind):
    """Spec §32: not every search result is a person."""
    assert classify(url, detect_platform(url)) is kind


def test_discover_deduplicates_across_queries():
    results = [
        ProviderResult(
            url="https://www.instagram.com/anna/?utm_source=brave",
            title="Anna",
            snippet="",
            query="q1",
            provider="fixture",
        ),
        ProviderResult(
            url="https://instagram.com/anna",
            title="Anna",
            snippet="",
            query="q2",
            provider="fixture",
        ),
    ]

    discovered = discover(results)

    assert len(discovered) == 1
    assert discovered[0].query == "q1"  # first sighting wins


# -------------------------------------------------------------------- dedup


def lead(name: str, score: int, platform: Platform, url: str, email: str | None = None) -> Lead:
    return Lead(
        id=f"lead_{name}_{platform.value}",
        user_id="user_demo",
        search_id="srch_test",
        search_name="test",
        name=name,
        headline="",
        summary="",
        score=score,
        platforms=[LeadPlatform(platform=platform, url=url)],
        contacts=LeadContacts(email=email),
    )


def test_one_person_found_twice_becomes_one_lead():
    """Spec §45: four platforms for one human must not be four leads."""
    instagram = lead("anna", 80, Platform.INSTAGRAM, "https://instagram.com/anna", "a@x.com")
    linkedin = lead("anna", 91, Platform.LINKEDIN, "https://linkedin.com/in/anna", "a@x.com")

    merged, duplicates = deduplicate([instagram, linkedin])

    assert duplicates == 1
    assert len(merged) == 1
    assert merged[0].score == 91  # the richer record survives
    assert {entry.platform for entry in merged[0].platforms} == {
        Platform.INSTAGRAM,
        Platform.LINKEDIN,
    }


def test_different_people_are_not_merged():
    merged, duplicates = deduplicate(
        [
            lead("anna", 80, Platform.INSTAGRAM, "https://instagram.com/anna"),
            lead("elena", 80, Platform.INSTAGRAM, "https://instagram.com/elena"),
        ]
    )

    assert duplicates == 0
    assert len(merged) == 2


def test_the_same_url_with_tracking_noise_is_one_lead():
    merged, _ = deduplicate(
        [
            lead("anna", 80, Platform.INSTAGRAM, "https://instagram.com/anna/"),
            lead("anna", 70, Platform.INSTAGRAM, "https://www.instagram.com/anna?utm_source=x"),
        ]
    )

    assert len(merged) == 1


# ------------------------------------------------------------ query generation


def test_query_generator_produces_several_targeted_queries():
    from app.models.common import SourceKind
    from app.models.search import SearchCriteria

    criteria = SearchCriteria(
        industry=["beauty"],
        business_types=["MLM"],
        keywords=["MIHI", "network marketing"],
        negative_keywords=["customer", "shop"],
        location={"country": "Spain"},
        sources=[SourceKind.INSTAGRAM_PUBLIC, SourceKind.LINKEDIN_PUBLIC, SourceKind.BLOGS],
    )

    queries = TemplateQueryGenerator().generate(criteria)

    assert len(queries) > 3
    assert len(set(queries)) == len(queries)
    assert any(query.startswith("site:instagram.com") for query in queries)
    assert any("site:linkedin.com/in" in query for query in queries)
    assert all('-"customer"' in query for query in queries)  # negatives on every query
    assert all("Spain" in query for query in queries)


# -------------------------------------------------------------------- retries


async def test_retry_recovers_from_a_transient_failure():
    attempts = {"count": 0}

    async def flaky() -> str:
        attempts["count"] += 1
        if attempts["count"] < 2:
            raise TimeoutError("429")
        return "ok"

    assert await retry_async(flaky, attempts=3, base_delay=0) == "ok"
    assert attempts["count"] == 2


async def test_retry_gives_up_instead_of_looping_forever():
    calls = {"count": 0}

    async def always_fails() -> None:
        calls["count"] += 1
        raise TimeoutError("still 429")

    with pytest.raises(TimeoutError):
        await retry_async(always_fails, attempts=3, base_delay=0)
    assert calls["count"] == 3
