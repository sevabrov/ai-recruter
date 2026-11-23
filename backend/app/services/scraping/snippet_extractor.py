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

Phase 5 added `ScrapeGraphProfileExtractor`, which reads the page itself. This one
did not become dead code, because the spec is explicit that not every social URL
can be scraped: when the page will not open, the search result is still the best
evidence available, and a lead built from it beats no lead at all. Which of the two
produced a profile is recorded on it (`extractor`), so the difference is never
guesswork — see `services/scraping/fallback.py`.
"""

import hashlib
import re
import unicodedata
from datetime import UTC, datetime
from urllib.parse import urlparse

from app.core.logging import get_logger
from app.models.common import GeoLocation, Platform, SignalType
from app.models.lead import LeadContacts, LeadPlatform, LeadSignal
from app.models.profile import ExtractedProfile
from app.models.source import DiscoveredUrl, LeadSource, UrlKind
from app.services.extraction.language import spoken
from app.services.extraction.vocabulary import (
    ACTIVE_WITHIN_DAYS,
    BRAND_FOLLOWERS,
    DATED_ACTIVITY_CONFIDENCE,
    find_place,
    find_terms,
    quote,
)
from app.services.scraping.base import ProfileExtractor
from app.services.scraping.names import clean as _clean
from app.services.scraping.names import commercial as _commercial
from app.services.scraping.names import looks_like_a_person as _looks_like_a_person
from app.services.scraping.names import plausible_name as _plausible_name
from app.services.search.markets import country_from_host, language_name

log = get_logger(__name__)

#: The ceiling for anything read out of a search snippet. Certainty needs a page.
MAX_CONFIDENCE = 0.65

HANDLE_ANYWHERE = re.compile(r"\(@(?P<handle>[\w.\-]{2,40})\)")
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
        # The city counts: a bio says "Київ" far more often than it says "Ukraine",
        # and a country filter reading only country names would call that unknown.
        located = find_place(text)
        # Failing that, where the address itself is registered: `ua.linkedin.com`,
        # `oksana.com.ua`. Weaker than a bio, and the only evidence a two-line
        # search result often carries.
        registered = None if located else country_from_host(urlparse(url.url).netloc)
        email = EMAIL.search(url.snippet)
        owns_site = url.platform in (Platform.WEBSITE, Platform.BLOG)

        return ExtractedProfile(
            url=url.url,
            canonical_url=url.canonical_url,
            platform=url.platform,
            name=name,
            headline=headline,
            company=company,
            location=GeoLocation(country=located[0] if located else registered),
            # The index's own language tag is a fact about the page, not a guess —
            # but it is a crawler's verdict on a whole page, and a Ukrainian bio
            # under an English page tag is common enough that the text gets a
            # second opinion. Both are kept (`extraction/language.py`).
            languages=spoken([language_name(url.language)], text),
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
            observations=_observations(
                url, text, followers=followers, located=located, registered=registered
            ),
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

    What the title actually looks like, though, is `Оксана | Косметолог
    (@oksana.beauty) • Instagram photos and videos`: the display name is a name
    *and* a self-description, separated by a pipe or a bullet. Requiring the whole
    prefix to read like a name refused most real profiles while accepting
    `Nu Skin Ukraine (@nuskin.ua)`, which is exactly backwards — 51 of 58
    candidates in one measured run were dropped here.

    So the handle is found wherever it is, the display name is read from the
    segment in front of it, and the role after the separator becomes the headline
    it always was. A profile with no display name at all keeps its handle as its
    identity: it is what the platform publishes and what a message is addressed
    to, which beats losing the person.
    """
    in_title = HANDLE_ANYWHERE.search(url.title)
    in_text = None if in_title else HANDLE_IN_TEXT.search(url.snippet)
    if in_title is not None:
        handle, prefix = in_title.group("handle"), url.title[: in_title.start()]
    elif in_text is not None:
        handle, prefix = in_text.group("handle"), in_text.group("name")
    elif from_url := _account(url):
        # An account with no display name is titled by its username and nothing
        # else — "oksana.mlm • Instagram photos and videos" — so the handle comes
        # from the URL, which is where it was all along.
        handle, prefix = from_url, url.title
    else:
        return None

    if _commercial(handle):
        return None

    parts = _segments(prefix)
    name = next((part for part in parts if _plausible_name(part)), "")
    headline = next((part for part in parts if part != name), None)
    if not name:
        # No display name to read. `@handle` is not a guess at a person's name — it
        # is the account, and on Instagram it is also the address a message goes to.
        name = f"@{handle}"
        if _commercial(name):
            return None
    return name, handle, headline, None


def _account(url: DiscoveredUrl) -> str | None:
    """The handle in the URL, when the path is just one — that is the profile."""
    segments = [segment for segment in urlparse(url.canonical_url).path.split("/") if segment]
    if len(segments) != 1:
        return None
    handle = segments[0].lstrip("@")
    return handle if re.fullmatch(r"[\w.\-]{2,40}", handle) else None


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
    if not parts:
        return None
    if _looks_like_a_person(parts[0]):
        return parts[0], None, parts[1] if len(parts) > 1 else None, None
    # A public figure's page is titled with the name *and* what they do, in one
    # phrase: "Piotr Krenig o przedsiębiorczości, marketingu i rozwoju". The name
    # is the capitalised words in front; it is accepted only when the page's own
    # address spells it too (`facebook.com/PiotrKrenigPrzedsiebiorca`), so a
    # phrase that merely starts with two capitalised words does not become a name.
    leading = _leading_name(parts[0])
    if leading and _in_address(leading, url.canonical_url):
        rest = parts[0][len(leading) :].strip(" ,-–—")
        return leading, None, rest or (parts[1] if len(parts) > 1 else None), None
    return None


def _leading_name(text: str) -> str | None:
    """
    Two or three capitalised words at the front of a longer phrase, ended by a
    lowercase word ("Piotr Krenig o …"), or None.
    """
    words = (text or "").split()
    for size in (3, 2):
        if len(words) > size and words[size][:1].islower():
            candidate = " ".join(words[:size]).strip(" ,")
            if _looks_like_a_person(candidate):
                return candidate
    return None


def _in_address(name: str, canonical_url: str) -> bool:
    """Whether the address spells the name, accents and spaces aside."""
    path = _fold(urlparse(canonical_url).path)
    return bool(path) and _fold(name) in path


def _fold(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text.replace("ł", "l").replace("Ł", "L"))
    return "".join(ch for ch in decomposed if ch.isalnum()).casefold()


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
    registered: str | None = None,
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
    elif registered:
        # Lower, because a domain says where an account was registered, not where
        # its owner lives — but it is a fact and it can be quoted.
        host = urlparse(url.url).netloc
        sightings[SignalType.LOCATION] = (0.3, f"The address {host} belongs to {registered}.")

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
            return DATED_ACTIVITY_CONFIDENCE, f"Search index reports the page as updated {when}"

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
