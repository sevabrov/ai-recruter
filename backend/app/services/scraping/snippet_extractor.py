"""
Search-result extractor — what a real search gives us before any page is fetched.

Phase 4 turns on live web search, and Phase 5 is what reads the pages behind the
results. Something has to stand between the two, or a live search would find real
people and report none of them: this extractor builds a profile from the *result
metadata the search API already returned* — the title, the description, the index's
page age and language — and nothing else. It never opens a URL.

That constraint is what makes it honest rather than a fake:

* `extractor: "snippet"` is recorded on every profile it produces;
* confidences are capped well below certainty, because a description is not a page;
* a title it cannot read a person's name out of returns `None`, exactly like a
  blocked page — a shop, a company account or an article does not become a lead.

Identity comes from the shapes the platforms actually publish:

    Anna López (@anna.beauty) • Instagram photos and videos
    Anna López - Beauty Coach - MIHI Iberia | LinkedIn
    Anna López | Facebook
    Anna López (@anna.lopez) on Threads

Phase 5 replaces this class with `ScrapeGraphProfileExtractor`, which reads the
page itself and can fill the fields this one has to leave empty.
"""

import hashlib
import re
from datetime import UTC, datetime

from app.core.logging import get_logger
from app.models.common import GeoLocation, Platform, SignalType
from app.models.lead import LeadContacts, LeadPlatform, LeadSignal
from app.models.profile import ExtractedProfile
from app.models.source import DiscoveredUrl, LeadSource, UrlKind
from app.services.extraction.vocabulary import (
    ACTIVE_WITHIN_DAYS,
    BRAND_FOLLOWERS,
    find_country,
    find_terms,
    quote,
)
from app.services.scraping.base import ProfileExtractor
from app.services.search.markets import language_name

log = get_logger(__name__)

#: The ceiling for anything read out of a search snippet. Certainty needs a page.
MAX_CONFIDENCE = 0.65

#: Words that mean the title is not a person, whatever else it looks like.
NOT_A_PERSON = {
    "about",
    "academy",
    "agency",
    "blog",
    "boutique",
    "careers",
    "clinic",
    "company",
    "contact",
    "products",
    "profiles",
    "shop",
    "store",
    "team",
    "gmbh",
    "ltd",
    "llc",
    "inc",
    "srl",
    "official",
    "login",
    "sign",
    "photos",
    "videos",
    "instagram",
    "facebook",
    "linkedin",
    "threads",
}

#: A brand's own account is the single most common false positive in a search for
#: people: it ranks high, its title reads like a name and its handle gives it away.
#: Localised, because the account is in the country being searched.
BRAND_MARKERS = {
    "official",
    "oficial",
    "oficialna",
    "oficjalny",
    "offiziell",
    "ufficiale",
    "officiel",
    "brand",
    "tienda",
    "negozio",
    "sklep",
    "loja",
    "магазин",
    "cosmetics",
    "cosmetica",
    "cosmética",
}

#: Lowercase in the middle of a name is normal: "Ana de la Cruz", "Jan van Dijk".
PARTICLES = {"de", "del", "della", "di", "da", "dos", "la", "le", "van", "von", "der", "den", "bin"}

HANDLE_IN_TITLE = re.compile(r"^(?P<name>[^(|•·]{2,60}?)\s*\(@(?P<handle>[\w.\-]{2,40})\)")
HANDLE_IN_TEXT = re.compile(
    r"(?:from|de)\s+(?P<name>[^(|•·]{2,60}?)\s*\(@(?P<handle>[\w.\-]{2,40})\)"
)
SEPARATORS = re.compile(r"\s+[-–—|·:]\s+|\s+[|•]\s*")
FOLLOWERS = re.compile(
    r"([\d][\d\s.,]*[KkMm]?)\s*(?:followers|follower|seguidores|seguidori|abonnenten"
    r"|obserwując\w*|подписчик\w*)",
    re.IGNORECASE,
)
POSTS = re.compile(
    r"([\d][\d\s.,]*[KkMm]?)\s*(?:posts|publicaciones|beiträge|post[iy]|публикаци\w*)",
    re.IGNORECASE,
)
EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]{2,}")
TRAILING_PLATFORM = re.compile(
    r"\s*[|•·]\s*(linkedin|facebook|instagram|threads|xing)\s*$", re.IGNORECASE
)


class SnippetProfileExtractor(ProfileExtractor):
    name = "snippet"

    async def extract(self, url: DiscoveredUrl) -> ExtractedProfile | None:
        if url.kind not in (UrlKind.CANDIDATE, UrlKind.UNKNOWN):
            return None

        identity = _identity(url)
        if identity is None:
            log.info("snippet_not_a_person", extra={"url": url.canonical_url})
            return None

        name, handle, headline, company = identity
        text = " ".join(part for part in (url.title, url.snippet) if part)
        followers = _count(FOLLOWERS, url.snippet)
        located = find_country(text)
        email = EMAIL.search(url.snippet)
        owns_site = url.platform in (Platform.WEBSITE, Platform.BLOG)

        return ExtractedProfile(
            url=url.url,
            canonical_url=url.canonical_url,
            platform=url.platform,
            name=name,
            headline=headline,
            company=company,
            location=GeoLocation(country=located[0]) if located else GeoLocation(),
            # The index's own language tag is a fact about the page, not a guess.
            languages=[language for language in [language_name(url.language)] if language],
            summary=(url.snippet or url.title)[:400],
            platforms=[
                LeadPlatform(
                    platform=url.platform,
                    handle=f"@{handle}" if handle else None,
                    url=url.url,
                    followers=followers,
                )
            ],
            sources=[
                LeadSource(
                    id=f"src_{hashlib.sha1(url.canonical_url.encode()).hexdigest()[:10]}",
                    platform=url.platform,
                    url=url.url,
                    title=url.title,
                    snippet=url.snippet,
                    discovered_at=datetime.now(UTC),
                )
            ],
            contacts=LeadContacts(
                email=email.group(0) if email else None,
                website=url.url if owns_site else None,
            ),
            observations=_observations(url, text, followers=followers, located=located),
            extractor=self.name,
        )


# -------------------------------------------------------------------- identity
def _identity(url: DiscoveredUrl) -> tuple[str, str | None, str | None, str | None] | None:
    """`(name, handle, headline, company)`, or None when this is not a person."""
    if url.platform in (Platform.INSTAGRAM, Platform.THREADS):
        return _handle_profile(url)
    if url.platform is Platform.LINKEDIN:
        return _linkedin(url)
    if url.platform is Platform.FACEBOOK:
        return _facebook(url)
    return _own_site(url)


def _handle_profile(url: DiscoveredUrl) -> tuple[str, str | None, str | None, str | None] | None:
    """
    Instagram and Threads put the display name next to the handle, which is strong
    enough evidence to accept a name that a page title alone would not earn — many
    are written in lowercase, and some are a single word.
    """
    match = HANDLE_IN_TITLE.match(url.title) or HANDLE_IN_TEXT.search(url.snippet)
    if match is None:
        return None
    name, handle = _clean(match.group("name")), match.group("handle")
    if not _plausible_name(name) or _commercial(handle):
        return None
    return name, handle, None, None


def _linkedin(url: DiscoveredUrl) -> tuple[str, str | None, str | None, str | None] | None:
    """`Name - Headline - Company | LinkedIn`, with the tail localised or absent."""
    parts = _segments(url.title)
    if not parts:
        return None
    name = parts[0]
    if not _looks_like_a_person(name):
        return None

    handle = _slug(url.canonical_url, "in")
    headline = parts[1] if len(parts) > 1 else None
    # A third segment is the employer often enough to record, never to trust: it is
    # only ever shown next to the source link it came from.
    company = parts[2] if len(parts) > 2 else None
    return name, handle, headline, company


def _facebook(url: DiscoveredUrl) -> tuple[str, str | None, str | None, str | None] | None:
    parts = _segments(url.title)
    if not parts or not _looks_like_a_person(parts[0]):
        return None
    return parts[0], None, parts[1] if len(parts) > 1 else None, None


def _own_site(url: DiscoveredUrl) -> tuple[str, str | None, str | None, str | None] | None:
    """
    A personal site is the one place the title is unstructured, so the bar is the
    strict one: some segment has to read like a person's name, and the longest of
    the others becomes the headline.
    """
    parts = _segments(url.title)
    named = next((part for part in parts if _looks_like_a_person(part)), None)
    if named is None:
        return None
    rest = [part for part in parts if part != named]
    headline = max(rest, key=len) if rest else None
    return named, None, headline, None


def _segments(title: str) -> list[str]:
    cleaned = TRAILING_PLATFORM.sub("", _clean(title))
    return [segment for part in SEPARATORS.split(cleaned) if (segment := _clean(part))]


def _clean(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip(" \t\n\r-–—|·•,")


def _looks_like_a_person(text: str) -> bool:
    """Two to four name-shaped words. Deliberately strict: a false name is a lead."""
    words = text.split()
    if not 2 <= len(words) <= 4 or len(text) > 60:
        return False
    if _commercial(text):
        return False
    if any(character.isdigit() for character in text):
        return False
    return all(word[0].isupper() or word.lower() in PARTICLES for word in words)


def _plausible_name(text: str) -> bool:
    """The lighter check, for titles where a handle already vouches for the name."""
    words = text.split()
    if not words or len(words) > 5 or len(text) > 60:
        return False
    if _commercial(text):
        return False
    return any(character.isalpha() for character in text)


def _commercial(text: str) -> bool:
    """A page or an account belonging to a business rather than to a person."""
    tokens = {token for token in re.split(r"[^\w]+", text.lower()) if token}
    return bool(tokens & (NOT_A_PERSON | BRAND_MARKERS))


def _slug(canonical_url: str, marker: str) -> str | None:
    parts = [part for part in canonical_url.split("/") if part]
    if marker in parts:
        index = parts.index(marker)
        return parts[index + 1] if index + 1 < len(parts) else None
    return None


# ---------------------------------------------------------------- observations
def _observations(
    url: DiscoveredUrl,
    text: str,
    *,
    followers: int | None,
    located: tuple[str, str] | None,
) -> list[LeadSignal]:
    """
    One sighting per signal the product scores, `detected=False` included — "we
    looked and found nothing" is information, and it keeps the lead page from
    implying that an absent signal was never checked.
    """
    terms = find_terms(text)
    sightings: dict[SignalType, tuple[float, str]] = {}

    for signal, hits in terms.items():
        sightings[signal] = (
            min(MAX_CONFIDENCE, 0.35 + 0.1 * len(hits)),
            quote(text, hits[0]),
        )

    if located:
        sightings[SignalType.LOCATION] = (0.5, quote(text, located[1]))

    brand = _personal_brand(url, followers, sightings.get(SignalType.PERSONAL_BRAND))
    if brand:
        sightings[SignalType.PERSONAL_BRAND] = brand

    active = _activity(url, text)
    if active:
        sightings[SignalType.ACTIVITY] = active

    return [
        LeadSignal(
            type=signal,
            detected=signal in sightings,
            confidence=sightings[signal][0] if signal in sightings else 0.0,
            evidence=sightings[signal][1] if signal in sightings else None,
            source_url=url.url,
            source_platform=url.platform,
        )
        for signal in SignalType
    ]


def _personal_brand(
    url: DiscoveredUrl, followers: int | None, from_terms: tuple[float, str] | None
) -> tuple[float, str] | None:
    """An audience or a place of their own — both are visible without the page."""
    if followers and followers >= BRAND_FOLLOWERS:
        return min(MAX_CONFIDENCE, 0.5), f"{followers:,} followers on {url.platform.value}"
    if from_terms:
        return from_terms
    if url.platform in (Platform.WEBSITE, Platform.BLOG):
        return 0.4, f"Publishes under their own domain: {url.canonical_url}"
    return None


def _activity(url: DiscoveredUrl, text: str) -> tuple[float, str] | None:
    """
    Recency, from the only two things a search result can say about it: when the
    index last saw the page, and how much the person has published.
    """
    if url.page_age:
        age = datetime.now(UTC) - _aware(url.page_age)
        if age.days <= ACTIVE_WITHIN_DAYS:
            when = url.age_label or url.page_age.date().isoformat()
            return 0.55, f"Search index reports the page as updated {when}"

    posts = _count(POSTS, text)
    if posts:
        return 0.4, f"{posts:,} posts published on {url.platform.value}"
    return None


def _aware(moment: datetime) -> datetime:
    """Brave omits the timezone about as often as it sends one."""
    return moment if moment.tzinfo else moment.replace(tzinfo=UTC)


def _count(pattern: re.Pattern[str], text: str) -> int | None:
    """`1,234` / `12.5K` / `3 M` → an integer, or None when there is no number."""
    match = pattern.search(text or "")
    if match is None:
        return None
    raw = match.group(1).strip().replace(" ", "")
    multiplier = {"k": 1_000, "m": 1_000_000}.get(raw[-1:].lower(), 1)
    if multiplier > 1:
        raw = raw[:-1]
    digits = raw.replace(",", ".") if multiplier > 1 else re.sub(r"[.,]", "", raw)
    try:
        return int(float(digits) * multiplier)
    except ValueError:
        return None
