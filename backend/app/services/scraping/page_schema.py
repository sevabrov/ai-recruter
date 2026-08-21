"""
The strict extraction schema (spec §34) and the prompt that asks for it.

    URL → ScrapeGraphAI Extract → this shape → ExtractedProfile

"Do not allow free-form response if structured extraction can be used": the model
is handed this schema and can only answer inside it. Every field is nullable and
defaults to "not found", because the one thing that must never happen is a filled
field that the page did not support — a guessed country is worse than an empty one.

Two deliberate differences from the example in §34:

* each signal carries its own `evidence` quote, not just a boolean. §36 requires
  evidence per signal, and a boolean with nothing behind it cannot be shown to a
  user or re-checked later. A claim that arrives without a quote is dropped here.
* `links` is asked for as well. It is what makes one person on two platforms one
  lead: an Instagram bio linking to a personal site gives the deduplicator a
  strong key that a search snippet never carries (spec §45).

The mapping into `ExtractedProfile` is in this file too, so the schema and its
interpretation cannot drift apart.
"""

import hashlib
import json
import re
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlparse

from pydantic import BaseModel, Field

from app.models.common import GeoLocation, Platform, SignalType
from app.models.lead import LeadContacts, LeadPlatform, LeadSignal
from app.models.profile import ExtractedProfile
from app.models.source import DiscoveredUrl, LeadSource
from app.services.extraction.vocabulary import ACTIVE_WITHIN_DAYS, BRAND_FOLLOWERS, find_country
from app.services.scraping.names import commercial, plausible_name
from app.services.search.markets import language_name

#: A page read by a model is strong evidence, and still not a certainty: the model
#: summarised what it saw. Phase 6 re-judges the same text with the signal detector.
MAX_CONFIDENCE = 0.9

#: Confidence for a claim the page supports with a quote.
QUOTED = 0.8
#: Structural facts (a follower count, a domain of one's own, a country in the bio).
OBSERVED = 0.75

#: How long a quote may be before it stops being a quote.
MAX_EVIDENCE_CHARS = 300

EXTRACTION_PROMPT = """
You are reading one public web page to decide whether it belongs to a specific
person who could be recruited into a beauty / network-marketing business.

Fill the provided schema and nothing else. Rules:
- Use only what this page states. Never guess, infer or complete from knowledge.
- If the page does not state something, leave it null / false / empty.
- is_person is true only for a page about one individual human. A brand account,
  a shop, a company page, a product listing, a login wall or an article is false.
- For every signal, `evidence` must be a short verbatim quote from the page, in the
  page's own language. A signal without a quote counts as not detected.
- `name` is the person's display name, without titles, emoji or handles.
- `links` are the outbound links the person publishes about themselves (their site,
  their other profiles, their link-in-bio target) — not navigation or share links.
""".strip()

SOCIAL_HOSTS = (
    "instagram.com",
    "linkedin.com",
    "facebook.com",
    "threads.net",
    "threads.com",
    "twitter.com",
    "x.com",
    "tiktok.com",
    "youtube.com",
    "t.me",
    "wa.me",
)


class PageClaim(BaseModel):
    detected: bool = Field(default=False, description="True only if the page shows this")
    evidence: str | None = Field(default=None, description="Short verbatim quote from the page")


class PageLocation(BaseModel):
    country: str | None = Field(default=None, description="Country in English, e.g. Spain")
    city: str | None = Field(default=None, description="City as written on the page")


class PageSignals(BaseModel):
    """The seven things the product scores; §36 wants each one judged separately."""

    mlm: PageClaim = Field(
        default_factory=PageClaim,
        description="Network marketing / MLM / direct sales / distributor activity",
    )
    beauty: PageClaim = Field(
        default_factory=PageClaim, description="Beauty, cosmetics, skincare relevance"
    )
    recruiting: PageClaim = Field(
        default_factory=PageClaim, description="Invites others to join a team or business"
    )
    leadership: PageClaim = Field(
        default_factory=PageClaim, description="Leads, mentors or manages a team"
    )
    personal_brand: PageClaim = Field(
        default_factory=PageClaim, description="Publishes as themselves: audience, blog, own site"
    )
    activity: PageClaim = Field(
        default_factory=PageClaim, description="Recent activity with a date the page states"
    )


class PageContacts(BaseModel):
    email: str | None = Field(default=None, description="Public e-mail address on the page")
    website: str | None = Field(default=None, description="Their own website, if linked")
    phone: str | None = Field(default=None, description="Public phone number on the page")


class PageExtraction(BaseModel):
    """What one page is allowed to say. Anything not in here is not collected."""

    is_person: bool = Field(default=False, description="This page is about one individual person")
    name: str | None = Field(default=None, description="The person's display name")
    headline: str | None = Field(default=None, description="Their own one-line description")
    company: str | None = Field(default=None, description="Company or brand they work with")
    summary: str | None = Field(default=None, description="Two sentences, from the page only")
    location: PageLocation = Field(default_factory=PageLocation)
    languages: list[str] = Field(
        default_factory=list, description="Languages the page is written in, in English"
    )
    handle: str | None = Field(default=None, description="Their username on this platform")
    followers: int | None = Field(default=None, description="Follower count shown on the page")
    posts: int | None = Field(default=None, description="Number of posts shown on the page")
    signals: PageSignals = Field(default_factory=PageSignals)
    contacts: PageContacts = Field(default_factory=PageContacts)
    links: list[str] = Field(default_factory=list, description="Outbound links they publish")


def output_schema() -> dict[str, Any]:
    """The JSON Schema handed to the provider as `output_schema`."""
    return PageExtraction.model_json_schema()


def content_hash(payload: Any) -> str:
    """
    Fingerprint of what the page yielded (spec §53). Sorted keys, so the same page
    read twice hashes the same and an unchanged page is visible as unchanged.
    """
    encoded = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(encoded.encode()).hexdigest()[:32]


def is_a_person(page: PageExtraction) -> bool:
    """
    The page's own claim, checked. A brand page that calls itself a person is the
    case this guards: the name and the handle still read as a business.
    """
    name = (page.name or "").strip()
    if not page.is_person or not name:
        return False
    if commercial(name) or commercial(page.handle or ""):
        return False
    return plausible_name(name)


def to_profile(page: PageExtraction, url: DiscoveredUrl, extractor: str) -> ExtractedProfile:
    """The read page as the profile the rest of the pipeline consumes."""
    located = _location(page, url)
    return ExtractedProfile(
        url=url.url,
        canonical_url=url.canonical_url,
        platform=url.platform,
        name=(page.name or "").strip(),
        headline=_trim(page.headline, 200),
        company=_trim(page.company, 200),
        location=located,
        languages=_languages(page, url),
        summary=_trim(page.summary, 400) or _trim(url.snippet, 400),
        platforms=[
            LeadPlatform(
                platform=url.platform,
                handle=_handle(page.handle),
                url=url.url,
                followers=page.followers if (page.followers or 0) > 0 else None,
            )
        ],
        sources=[
            LeadSource(
                id=f"src_{hashlib.sha1(url.canonical_url.encode()).hexdigest()[:10]}",
                platform=url.platform,
                url=url.url,
                title=url.title,
                snippet=_trim(page.summary, 400) or url.snippet,
                discovered_at=datetime.now(UTC),
            )
        ],
        contacts=_contacts(page, url),
        observations=_observations(page, url, located),
        extractor=extractor,
    )


# --------------------------------------------------------------------- mapping
def _location(page: PageExtraction, url: DiscoveredUrl) -> GeoLocation:
    """
    The page's own words first; the search result's text only as a fallback, and
    only for the country — a city guessed from a snippet is a guess.
    """
    country = _trim(page.location.country, 120)
    if country:
        # "España" on the page is stored as Spain, so the filters can group it.
        recognised = find_country(country)
        return GeoLocation(
            country=recognised[0] if recognised else country, city=_trim(page.location.city, 120)
        )
    fallback = find_country(" ".join(part for part in (url.title, url.snippet) if part))
    return GeoLocation(
        country=fallback[0] if fallback else None, city=_trim(page.location.city, 120)
    )


def _languages(page: PageExtraction, url: DiscoveredUrl) -> list[str]:
    named = [
        language.strip().title()
        for language in page.languages
        if isinstance(language, str) and language.strip()
    ]
    indexed = language_name(url.language)
    if indexed and indexed not in named:
        named.append(indexed)
    return list(dict.fromkeys(named))[:5]


def _handle(handle: str | None) -> str | None:
    cleaned = (handle or "").strip().lstrip("@")
    return f"@{cleaned}" if cleaned else None


def _contacts(page: PageExtraction, url: DiscoveredUrl) -> LeadContacts:
    """
    A website is a merge key (spec §45), so both sides of a merge have to write it
    the same way: the site's *origin*, not the page inside it. Otherwise the same
    person's `luciaferrer.es/about` and an Instagram bio's `luciaferrer.es` would
    stay two leads. The exact page is never lost — it is in `sources`.
    """
    own_site = page.contacts.website or _own_link(page.links)
    if not own_site and url.platform in (Platform.WEBSITE, Platform.BLOG):
        own_site = url.canonical_url
    return LeadContacts(
        email=_email(page.contacts.email),
        website=_origin(own_site),
        phone=_trim(page.contacts.phone, 64),
    )


def _own_link(links: list[str]) -> str | None:
    """The first link that is a site of their own rather than another social profile."""
    for link in links:
        if not isinstance(link, str) or not link.startswith(("http://", "https://")):
            continue
        host = urlparse(link).netloc.lower().removeprefix("www.")
        if not any(host == social or host.endswith(f".{social}") for social in SOCIAL_HOSTS):
            return link
    return None


def _origin(url: str | None) -> str | None:
    if not url:
        return None
    candidate = url if url.startswith(("http://", "https://")) else f"https://{url}"
    parsed = urlparse(candidate)
    host = parsed.netloc.lower().removeprefix("www.")
    return f"{parsed.scheme}://{host}" if host else None


def _email(value: str | None) -> str | None:
    match = re.search(r"[\w.+-]+@[\w-]+\.[\w.-]{2,}", value or "")
    return match.group(0) if match else None


# ---------------------------------------------------------------- observations
def _observations(
    page: PageExtraction, url: DiscoveredUrl, located: GeoLocation
) -> list[LeadSignal]:
    """
    One sighting per scored signal, `detected=False` included — "we read the page
    and it says nothing about this" is information the lead screen shows (spec §34).

    A claim with no quote behind it is not detected. That single rule is what keeps
    a confident model from inventing a lead's whole profile.
    """
    claims = {
        SignalType.MLM: page.signals.mlm,
        SignalType.BEAUTY: page.signals.beauty,
        SignalType.RECRUITING: page.signals.recruiting,
        SignalType.LEADERSHIP: page.signals.leadership,
        SignalType.PERSONAL_BRAND: page.signals.personal_brand,
        SignalType.ACTIVITY: page.signals.activity,
    }
    sightings: dict[SignalType, tuple[float, str]] = {}

    for signal, claim in claims.items():
        evidence = _trim(claim.evidence, MAX_EVIDENCE_CHARS)
        if claim.detected and evidence:
            sightings[signal] = (QUOTED, evidence)

    if located.country:
        where = ", ".join(part for part in (located.city, located.country) if part)
        sightings[SignalType.LOCATION] = (OBSERVED, f"The page places them in {where}")

    brand = _personal_brand(page, url)
    if brand and SignalType.PERSONAL_BRAND not in sightings:
        sightings[SignalType.PERSONAL_BRAND] = brand

    active = _activity(page, url)
    if active and SignalType.ACTIVITY not in sightings:
        sightings[SignalType.ACTIVITY] = active

    return [
        LeadSignal(
            type=signal,
            detected=signal in sightings,
            confidence=min(MAX_CONFIDENCE, sightings[signal][0]) if signal in sightings else 0.0,
            evidence=sightings[signal][1] if signal in sightings else None,
            source_url=url.url,
            source_platform=url.platform,
        )
        for signal in SignalType
    ]


def _personal_brand(page: PageExtraction, url: DiscoveredUrl) -> tuple[float, str] | None:
    """An audience or a place of their own, counted from the page rather than claimed."""
    followers = page.followers or 0
    if followers >= BRAND_FOLLOWERS:
        return OBSERVED, f"{followers:,} followers on {url.platform.value}"
    if url.platform in (Platform.WEBSITE, Platform.BLOG):
        return 0.6, f"Publishes under their own domain: {url.canonical_url}"
    return None


def _activity(page: PageExtraction, url: DiscoveredUrl) -> tuple[float, str] | None:
    """
    Recency the page did not state itself: when the search index last saw it, and
    how much the person has published.
    """
    if url.page_age:
        age = datetime.now(UTC) - _aware(url.page_age)
        if age.days <= ACTIVE_WITHIN_DAYS:
            when = url.age_label or url.page_age.date().isoformat()
            return 0.55, f"Search index reports the page as updated {when}"
    if (page.posts or 0) > 0:
        return 0.5, f"{page.posts:,} posts published on {url.platform.value}"
    return None


def _aware(moment: datetime) -> datetime:
    return moment if moment.tzinfo else moment.replace(tzinfo=UTC)


def _trim(value: str | None, limit: int) -> str | None:
    cleaned = re.sub(r"\s+", " ", value or "").strip()
    return cleaned[:limit] or None
