"""
URL normalization and candidate discovery (spec §31–32).

Search results arrive dirty: tracking parameters, trailing slashes, mixed case,
mobile hosts, and the same profile from four different queries. Everything
downstream (dedup, the scrape cache, cost) depends on one URL meaning one thing,
so normalization happens once, here, before anything is fetched.

Not every result is a person either, so URLs are classified rather than trusted.
The heuristics are intentionally simple and conservative — Phase 5 refines them
with what the extractor actually manages to read.
"""

import re
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from app.models.common import Platform
from app.models.source import DiscoveredUrl, ProviderResult, UrlKind

TRACKING_PREFIXES = ("utm_", "fbclid", "gclid", "mc_", "igshid", "ref_", "ref", "source")

PLATFORM_HOSTS: dict[str, Platform] = {
    "instagram.com": Platform.INSTAGRAM,
    "linkedin.com": Platform.LINKEDIN,
    "facebook.com": Platform.FACEBOOK,
    "threads.net": Platform.THREADS,
    "threads.com": Platform.THREADS,
}

#: Paths that are never a person's profile.
NON_PROFILE_SEGMENTS = {
    "instagram.com": {"p", "reel", "reels", "explore", "stories", "tv"},
    "linkedin.com": {"company", "school", "jobs", "posts", "pulse", "showcase"},
    "facebook.com": {"groups", "events", "marketplace", "watch", "photo", "story.php"},
}

BLOG_HINTS = ("/blog/", "medium.com", "substack.com", "wordpress.com", "blogspot.")
ARTICLE_HINTS = ("/news/", "/article/", "/press/", "/20")
PRODUCT_HINTS = ("/shop", "/tienda", "/product", "/cart", "/kaufen", "/negozio")


def canonicalize(url: str) -> str:
    """Strip tracking noise so `…/anna/` and `…/anna/?utm_source=x` are one URL."""
    parsed = urlparse(url.strip())
    host = parsed.netloc.lower().removeprefix("www.").removeprefix("m.")
    path = re.sub(r"/+", "/", parsed.path).rstrip("/") or "/"
    query = urlencode(
        [
            (key, value)
            for key, value in parse_qsl(parsed.query)
            if not key.lower().startswith(TRACKING_PREFIXES)
        ]
    )
    scheme = parsed.scheme or "https"
    return urlunparse((scheme, host, path, "", query, ""))


def detect_platform(url: str) -> Platform:
    host = urlparse(url).netloc.lower().removeprefix("www.").removeprefix("m.")
    for domain, platform in PLATFORM_HOSTS.items():
        if host == domain or host.endswith(f".{domain}"):
            return platform
    lowered = url.lower()
    if any(hint in lowered for hint in BLOG_HINTS):
        return Platform.BLOG
    return Platform.WEBSITE


def classify(url: str, platform: Platform) -> UrlKind:
    parsed = urlparse(url)
    host = parsed.netloc.lower().removeprefix("www.")
    segments = [segment for segment in parsed.path.split("/") if segment]
    lowered = url.lower()

    if platform in (Platform.INSTAGRAM, Platform.FACEBOOK, Platform.THREADS, Platform.LINKEDIN):
        blocked = next(
            (values for domain, values in NON_PROFILE_SEGMENTS.items() if host.endswith(domain)),
            set(),
        )
        if segments and segments[0].lower() in blocked:
            first = segments[0].lower()
            return UrlKind.COMPANY if first in {"company", "school"} else UrlKind.ARTICLE
        if platform is Platform.LINKEDIN:
            # Only /in/<slug> is a person on LinkedIn.
            is_person = segments[:1] == ["in"] and len(segments) > 1
            return UrlKind.CANDIDATE if is_person else UrlKind.UNKNOWN
        return UrlKind.CANDIDATE if len(segments) == 1 else UrlKind.UNKNOWN

    if any(hint in lowered for hint in PRODUCT_HINTS):
        return UrlKind.PRODUCT
    if any(hint in lowered for hint in ARTICLE_HINTS) or platform is Platform.BLOG:
        return UrlKind.ARTICLE
    return UrlKind.UNKNOWN


def discover(results: list[ProviderResult]) -> list[DiscoveredUrl]:
    """
    Normalize → identify platform → classify → deduplicate, in that order
    (spec §31). The first sighting of a canonical URL wins, so the query that
    found it first is the one recorded.
    """
    seen: dict[str, DiscoveredUrl] = {}
    for result in results:
        canonical = canonicalize(result.url)
        if canonical in seen:
            continue
        platform = detect_platform(canonical)
        seen[canonical] = DiscoveredUrl(
            url=result.url,
            canonical_url=canonical,
            platform=platform,
            kind=classify(canonical, platform),
            title=result.title,
            snippet=result.snippet,
            query=result.query,
            provider=result.provider,
        )
    return list(seen.values())


def candidates(urls: list[DiscoveredUrl]) -> list[DiscoveredUrl]:
    """
    URLs worth spending an extraction credit on. `unknown` is included on
    purpose — a personal website rarely looks like a profile, and dropping it
    would lose exactly the leads the public-web-first approach is after.
    """
    return [url for url in urls if url.kind in (UrlKind.CANDIDATE, UrlKind.UNKNOWN)]
