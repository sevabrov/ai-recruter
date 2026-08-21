"""
Reading a page with ScrapeGraphAI's v2 Extract API (spec §33–34, §51–52).

No test here reaches the network: the reader takes its HTTP client, so the
transport is a canned ScrapeGraphAI response. What is worth testing is not that the
service answers — it is what we do with each kind of answer, and there are five:
a person, a page that is not a person, a page that would not open, a service that
failed, and a model that answered outside the schema it was given.

The rule the whole file is built around: **nothing may be claimed that the page did
not say.** A confident model with no quote behind it is how invented leads happen.
"""

import json

import httpx
import pytest

from app.core.errors import ProviderAuthError, ProviderError, ProviderUnavailableError
from app.core.limits import RateLimiter
from app.core.retry import retry_async
from app.models.common import Platform, SignalType
from app.models.scrape import ScrapeOutcome
from app.models.source import DiscoveredUrl, UrlKind
from app.services.scraping.base import ExtractionCost
from app.services.scraping.page_schema import MAX_CONFIDENCE
from app.services.scraping.scrapegraph_extractor import ScrapeGraphProfileExtractor

TOKEN = "sgai-secret-token"

INSTAGRAM = DiscoveredUrl(
    url="https://www.instagram.com/lucia.mihi/?utm_source=brave",
    canonical_url="https://instagram.com/lucia.mihi",
    platform=Platform.INSTAGRAM,
    kind=UrlKind.CANDIDATE,
    title="Lucía Ferrer (@lucia.mihi) • Instagram photos and videos",
    snippet="8,420 Followers — network marketing y belleza",
    query="site:instagram.com MIHI Spain",
    provider="brave",
    language="es",
)

#: What the Extract service returns for that page, in the schema it was handed.
PERSON = {
    "is_person": True,
    "name": "Lucía Ferrer",
    "headline": "Líder de equipo · belleza y bienestar",
    "company": "MIHI Iberia",
    "summary": "Distribuidora independiente y mentora de equipo en Valencia.",
    "location": {"country": "España", "city": "Valencia"},
    "languages": ["spanish", "english"],
    "handle": "lucia.mihi",
    "followers": 8420,
    "posts": 512,
    "signals": {
        "mlm": {"detected": True, "evidence": "Distribuidora independiente de MIHI"},
        "beauty": {"detected": True, "evidence": "cosmética y cuidado de la piel"},
        "recruiting": {"detected": True, "evidence": "Únete a mi equipo"},
        "leadership": {"detected": True, "evidence": "Líder de equipo desde 2021"},
        "personal_brand": {"detected": True, "evidence": "Link in bio: luciaferrer.es"},
        "activity": {"detected": True, "evidence": "Última publicación: hace 2 días"},
    },
    "contacts": {"email": "hola@luciaferrer.es", "website": None, "phone": None},
    "links": ["https://www.instagram.com/mihi.oficial/", "https://luciaferrer.es/sobre-mi"],
}


def completed(extracted: dict | None = None, **extra) -> dict:
    """What `POST /api/extract` answers with: the extraction plus what it consumed."""
    return {
        "id": "8c34fc03-17be-4fcc-a7ce-6ebcab23ad43",
        "raw": None,
        "json": PERSON if extracted is None else extracted,
        "usage": {"promptTokens": 361, "completionTokens": 92},
        "metadata": {"chunker": {"chunks": [{"size": 33}]}, "fetch": {}},
        **extra,
    }


def refused(reason: str) -> dict:
    """A page that would not let us in: an empty extraction and a fetch diagnostic."""
    return {
        "id": "req_blocked",
        "raw": None,
        "json": {},
        "usage": {"promptTokens": 12, "completionTokens": 0},
        "metadata": {"fetch": {"note": reason}},
    }


def reader(handler, **kwargs) -> ScrapeGraphProfileExtractor:
    """A reader whose transport is a function, and whose throttle is off."""
    return ScrapeGraphProfileExtractor(
        TOKEN,
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
        rate_limit_per_second=0,
        **kwargs,
    )


def answers(payload: dict, status: int = 200):
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(status, json=payload)

    return handler


def recorder(payload: dict, status: int = 200):
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(status, json=payload)

    return seen, handler


def signal(profile, kind: SignalType):
    return next(entry for entry in profile.observations if entry.type is kind)


# ------------------------------------------------------------------- a person


async def test_a_read_page_becomes_the_profile_the_page_states():
    read = await reader(answers(completed())).read(INSTAGRAM)

    assert read.outcome is ScrapeOutcome.OK
    profile = read.profile
    assert profile is not None
    assert profile.name == "Lucía Ferrer"
    assert profile.headline == "Líder de equipo · belleza y bienestar"
    assert profile.company == "MIHI Iberia"
    # "España" on the page is stored as Spain, so the filters can group it.
    assert profile.location.country == "Spain"
    assert profile.location.city == "Valencia"
    assert profile.languages == ["Spanish", "English"]
    assert profile.platforms[0].handle == "@lucia.mihi"
    assert profile.platforms[0].followers == 8420
    assert profile.contacts.email == "hola@luciaferrer.es"
    # Read from the page, not from the search result — and it says so.
    assert profile.extractor == "scrapegraph"
    assert profile.sources[0].url == INSTAGRAM.url


async def test_the_page_is_fingerprinted_so_an_unchanged_page_is_visible_as_unchanged():
    first = await reader(answers(completed())).read(INSTAGRAM)
    again = await reader(answers(completed())).read(INSTAGRAM)
    other = await reader(answers(completed({**PERSON, "followers": 9001}))).read(INSTAGRAM)

    assert first.content_hash and first.content_hash == again.content_hash
    assert other.content_hash != first.content_hash


async def test_every_signal_is_reported_and_none_of_them_is_certain():
    read = await reader(answers(completed())).read(INSTAGRAM)
    profile = read.profile
    assert profile is not None

    assert {entry.type for entry in profile.observations} == set(SignalType)
    assert all(entry.confidence <= MAX_CONFIDENCE for entry in profile.observations)
    mlm = signal(profile, SignalType.MLM)
    assert mlm.detected is True
    assert mlm.evidence == "Distribuidora independiente de MIHI"
    assert mlm.source_url == INSTAGRAM.url
    assert mlm.source_platform is Platform.INSTAGRAM


async def test_a_claim_without_a_quote_behind_it_is_not_a_signal():
    """
    The whole file's rule. A model that says "yes, leadership" and cannot quote the
    page has told us nothing, and a lead page that showed it as detected would be
    presenting a guess as evidence (spec §16, §36).
    """
    silent = {
        **PERSON,
        "signals": {
            **PERSON["signals"],
            "leadership": {"detected": True, "evidence": None},
            "recruiting": {"detected": True, "evidence": "   "},
        },
    }

    profile = (await reader(answers(completed(silent))).read(INSTAGRAM)).profile

    assert profile is not None
    assert signal(profile, SignalType.LEADERSHIP).detected is False
    assert signal(profile, SignalType.RECRUITING).detected is False
    assert signal(profile, SignalType.MLM).detected is True  # this one was quoted


async def test_a_signal_the_page_is_silent_about_is_reported_as_not_found():
    quiet = {**PERSON, "signals": {}}

    profile = (await reader(answers(completed(quiet))).read(INSTAGRAM)).profile

    assert profile is not None
    absent = signal(profile, SignalType.RECRUITING)
    assert (absent.detected, absent.confidence, absent.evidence) == (False, 0.0, None)


async def test_the_link_they_publish_becomes_a_website_the_deduplicator_can_match():
    """
    This is what page reading buys that a snippet cannot (spec §45): the bio link is
    the strong key that makes an Instagram profile and a personal site one person.
    Stored as the site's origin, so both sides of the merge write it the same way.
    """
    profile = (await reader(answers(completed())).read(INSTAGRAM)).profile

    assert profile is not None
    # The first link is another social profile and is skipped; the second is theirs.
    assert profile.contacts.website == "https://luciaferrer.es"


# ---------------------------------------------------------- not a person, or not


async def test_a_page_that_is_not_a_person_is_settled_not_retried():
    shop = {**PERSON, "is_person": False, "name": "Tienda MIHI España"}

    read = await reader(answers(completed(shop))).read(INSTAGRAM)

    assert read.outcome is ScrapeOutcome.NOT_A_PERSON
    assert read.profile is None
    # Still fingerprinted: we know what this page said, and it will not be re-read.
    assert read.content_hash


@pytest.mark.parametrize(
    "name",
    ["MIHI España Oficial", "MIHI Cosmetics", "Beauty Shop Madrid"],
)
async def test_a_brand_that_calls_itself_a_person_is_still_a_brand(name):
    brand = {**PERSON, "is_person": True, "name": name, "handle": "mihi.oficial"}

    read = await reader(answers(completed(brand))).read(INSTAGRAM)

    assert read.outcome is ScrapeOutcome.NOT_A_PERSON


async def test_a_page_that_would_not_open_is_recorded_as_blocked():
    """
    v2 has no error field on a served request: a login wall comes back as an empty
    extraction, and `metadata.fetch` is what says why.
    """
    read = await reader(answers(refused("Login required: redirected to a sign in wall"))).read(
        INSTAGRAM
    )

    assert read.outcome is ScrapeOutcome.BLOCKED
    assert read.profile is None
    assert read.detail and "sign in" in read.detail


async def test_a_fetch_status_the_page_answered_with_counts_as_blocked_too():
    answered_403 = {"id": "r", "json": {}, "metadata": {"fetch": {"status": 403}}}

    read = await reader(answers(answered_403)).read(INSTAGRAM)

    assert read.outcome is ScrapeOutcome.BLOCKED
    assert read.detail == "The page answered 403"


async def test_an_empty_extraction_with_no_explanation_is_empty_not_blocked():
    """Guessing "blocked" from silence would overstate what we know."""
    read = await reader(answers(completed({}))).read(INSTAGRAM)

    assert read.outcome is ScrapeOutcome.EMPTY
    assert read.detail == "The page yielded no fields"


async def test_an_extraction_of_nothing_but_nulls_is_empty_not_a_lead():
    hollow = {
        "is_person": False,
        "name": None,
        "signals": {},
        "contacts": {"email": None},
        "links": [],
    }

    read = await reader(answers(completed(hollow))).read(INSTAGRAM)

    assert read.outcome is ScrapeOutcome.EMPTY
    assert read.profile is None


async def test_an_answer_outside_the_schema_is_an_unreadable_page_not_a_parse_error():
    """
    Reading a malformed answer loosely is exactly how invented data gets in, so a
    response that does not fit `PageExtraction` counts as a page we could not read.
    """
    nonsense = {"name": {"first": "Lucía"}, "followers": "loads", "signals": "yes"}

    read = await reader(answers(completed(nonsense))).read(INSTAGRAM)

    assert read.outcome is ScrapeOutcome.EMPTY
    assert read.profile is None


async def test_the_request_is_the_documented_v2_extract_call():
    seen, handler = recorder(completed())

    await reader(handler).read(INSTAGRAM)

    request = seen[0]
    assert request.method == "POST"
    body = json.loads(request.read())
    # v2 field names: url / prompt / schema (the legacy ones were website_url /
    # user_prompt / output_schema, and a rename would silently extract nothing).
    assert body["url"] == INSTAGRAM.canonical_url
    assert "person" in body["prompt"].lower()
    # Structured extraction, not a conversation (spec §34).
    assert "is_person" in body["schema"]["properties"]


# ------------------------------------------------------------------ the key


async def test_the_key_travels_in_a_header_and_appears_nowhere_else():
    seen, handler = recorder(completed())

    await reader(handler).read(INSTAGRAM)

    request = seen[0]
    assert request.headers["SGAI-APIKEY"] == TOKEN
    assert TOKEN not in str(request.url)
    assert TOKEN not in request.read().decode()


async def test_a_rejected_key_says_what_to_fix_and_costs_one_call():
    seen, handler = recorder(
        {"error": {"type": "auth_invalid_key", "message": "Invalid or deprecated API key"}},
        status=403,
    )
    page_reader = reader(handler)

    with pytest.raises(ProviderAuthError) as raised:
        await retry_async(lambda: page_reader.read(INSTAGRAM), attempts=3, base_delay=0)

    assert "SCRAPEGRAPH_API_KEY" in raised.value.message
    assert TOKEN not in raised.value.message
    assert len(seen) == 1  # retrying a bad key spends credits for nothing (§51)


async def test_an_empty_balance_is_not_retried_either():
    seen, handler = recorder(
        {
            "error": {
                "type": "insufficient_credits",
                "message": "Not enough credits to complete this request",
            }
        },
        status=402,
    )
    page_reader = reader(handler)

    with pytest.raises(ProviderError) as raised:
        await retry_async(lambda: page_reader.read(INSTAGRAM), attempts=3, base_delay=0)

    assert "credits" in raised.value.message
    assert raised.value.retryable is False
    assert len(seen) == 1


async def test_a_refused_request_repeats_what_the_provider_objected_to():
    """A 400 is our bug, and the message is the only thing that says which one."""
    _, handler = recorder(
        {
            "error": {
                "type": "invalid_format",
                "message": "Private or internal URLs are not allowed",
            }
        },
        status=400,
    )

    with pytest.raises(ProviderError) as raised:
        await reader(handler).read(INSTAGRAM)

    assert "Private or internal URLs" in raised.value.message
    assert raised.value.retryable is False


def test_the_reader_refuses_to_exist_without_a_key():
    with pytest.raises(ValueError):
        ScrapeGraphProfileExtractor("")


# ------------------------------------------------------------- when it fails


async def test_a_rate_limit_is_retryable_and_pushes_the_next_call_out():
    limiter = RateLimiter(0)
    calls: list[int] = []

    def handler(_: httpx.Request) -> httpx.Response:
        calls.append(1)
        return httpx.Response(
            429,
            headers={"Retry-After": "0.05"},
            json={"error": {"type": "rate_limited", "message": "Too many requests"}},
        )

    page_reader = reader(handler, limiter=limiter)

    with pytest.raises(ProviderUnavailableError) as raised:
        await page_reader.read(INSTAGRAM)

    assert raised.value.retryable is True
    # The provider knows when it will serve us again; the limiter now does too (§52).
    assert limiter._next_at > 0


async def test_an_outage_is_retried_but_bounded():
    seen, handler = recorder(
        {"error": {"type": "internal_error", "message": "An error occurred"}}, status=503
    )
    page_reader = reader(handler)

    with pytest.raises(ProviderUnavailableError):
        await retry_async(lambda: page_reader.read(INSTAGRAM), attempts=3, base_delay=0)

    assert len(seen) == 3  # never forever


async def test_a_timeout_is_a_provider_outage_not_a_crash():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("too slow", request=request)

    with pytest.raises(ProviderUnavailableError):
        await reader(handler).read(INSTAGRAM)


async def test_a_response_that_is_not_json_is_an_outage():
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="<html>maintenance</html>")

    with pytest.raises(ProviderUnavailableError):
        await reader(handler).read(INSTAGRAM)


# ------------------------------------------------------------------- what it cost


async def test_one_page_is_one_request_and_its_tokens_are_recorded():
    """v2 answers synchronously and reports what the extraction consumed (spec §54)."""
    seen, handler = recorder(completed())
    page_reader = reader(handler)

    await page_reader.read(INSTAGRAM)

    assert len(seen) == 1
    assert (page_reader.cost.credits, page_reader.cost.pages_read) == (1, 1)
    assert (page_reader.cost.tokens_in, page_reader.cost.tokens_out) == (361, 92)


async def test_a_page_that_yielded_nothing_was_still_billed():
    """The request was served; what the page contained is not the provider's problem."""
    page_reader = reader(answers(refused("login wall")))

    read = await page_reader.read(INSTAGRAM)

    assert read.outcome is ScrapeOutcome.BLOCKED
    assert page_reader.cost.credits == 1


async def test_a_rejected_request_is_not_billed():
    page_reader = reader(answers({"error": {"type": "internal_error", "message": "no"}}, 503))

    with pytest.raises(ProviderUnavailableError):
        await page_reader.read(INSTAGRAM)

    assert page_reader.cost.credits == 0


async def test_credits_are_counted_where_the_search_can_see_them():
    cost = ExtractionCost()
    page_reader = reader(answers(completed()), cost=cost)

    await page_reader.read(INSTAGRAM)
    await page_reader.read(INSTAGRAM.model_copy(update={"canonical_url": "https://x.example/a"}))

    # The shared counter the pipeline copies into the search's usage.
    assert (cost.pages_read, cost.credits, cost.pages_cached) == (2, 2, 0)
