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
from urllib.parse import parse_qsl, unquote, urlencode, urlparse, urlunparse

from app.models.common import Platform, SourceKind
from app.models.source import DiscoveredUrl, FoundPost, ProviderResult, UrlKind

TRACKING_PREFIXES = ("utm_", "fbclid", "gclid", "mc_", "igshid", "ref_", "ref", "source")

#: Which platforms each source the wizard offers actually covers. This is the
#: mapping that makes "only look where I said" enforceable rather than advisory.
PLATFORMS_BY_SOURCE: dict[SourceKind, set[Platform]] = {
    SourceKind.INSTAGRAM_PUBLIC: {Platform.INSTAGRAM},
    SourceKind.LINKEDIN_PUBLIC: {Platform.LINKEDIN},
    SourceKind.FACEBOOK_PUBLIC: {Platform.FACEBOOK},
    SourceKind.THREADS_PUBLIC: {Platform.THREADS},
    # The open web is where a personal site lives, and a personal site is a lead.
    SourceKind.PUBLIC_WEB: {Platform.WEBSITE, Platform.BLOG},
    SourceKind.COMPANY_WEBSITES: {Platform.WEBSITE},
    SourceKind.BLOGS: {Platform.BLOG},
}

PLATFORM_HOSTS: dict[str, Platform] = {
    "instagram.com": Platform.INSTAGRAM,
    "linkedin.com": Platform.LINKEDIN,
    "facebook.com": Platform.FACEBOOK,
    "threads.net": Platform.THREADS,
    "threads.com": Platform.THREADS,
}

#: The platforms that publish profiles in one documented address shape, so an
#: address that is not that shape is not a person we failed to recognise.
SOCIAL_PLATFORMS = {Platform.INSTAGRAM, Platform.FACEBOOK, Platform.THREADS, Platform.LINKEDIN}

#: Paths that are never a person's profile.
NON_PROFILE_SEGMENTS = {
    "instagram.com": {"p", "reel", "reels", "explore", "stories", "tv"},
    "linkedin.com": {"company", "school", "jobs", "posts", "pulse", "showcase"},
    "facebook.com": {
        "groups",
        "events",
        "marketplace",
        "watch",
        "photo",
        "story.php",
        "permalink.php",
        "reel",
        "share",
    },
}

BLOG_HINTS = ("/blog/", "medium.com", "substack.com", "wordpress.com", "blogspot.")
#: Path segments that mean "this is a publication about something", not somebody.
#: Matched as whole segments, because `/articles/` is exactly the URL that reached
#: the client's lead list while the substring `/article/` did not match it.
ARTICLE_SEGMENTS = {
    "article",
    "articles",
    "news",
    "novosti",
    "press",
    "publications",
    "stati",
    "story",
    "topic",
    "tag",
    "tags",
    "category",
    "новости",
    "новини",
    "статьи",
    "статті",
}
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

    if platform in SOCIAL_PLATFORMS:
        blocked = next(
            (values for domain, values in NON_PROFILE_SEGMENTS.items() if host.endswith(domain)),
            set(),
        )
        if segments and segments[0].lower() in blocked:
            first = segments[0].lower()
            return UrlKind.COMPANY if first in {"company", "school"} else UrlKind.ARTICLE
        if platform is Platform.FACEBOOK and _facebook_profile(segments, parsed.query):
            return UrlKind.CANDIDATE
        if platform is Platform.LINKEDIN:
            # Only /in/<slug> is a person on LinkedIn.
            is_person = segments[:1] == ["in"] and len(segments) > 1
            return UrlKind.CANDIDATE if is_person else UrlKind.UNKNOWN
        # One segment, and it has to look like somebody's handle. Without the shape
        # check, a run spent its budget on `instagram.com/accounts/login`,
        # `facebook.com/photo.php?fbid=…` and `facebook.com/581399108893746` — a
        # login form, a photograph and a page's internal id — and each arrived on
        # the results screen counted as "not a person", as though the search had
        # found somebody unsuitable rather than nothing at all.
        if len(segments) != 1:
            return UrlKind.UNKNOWN
        return UrlKind.CANDIDATE if _handle(segments[0]) else UrlKind.UNKNOWN

    if any(hint in lowered for hint in PRODUCT_HINTS):
        return UrlKind.PRODUCT
    if _is_article(segments) or platform is Platform.BLOG:
        return UrlKind.ARTICLE
    return UrlKind.UNKNOWN


def _facebook_profile(segments: list[str], query: str) -> bool:
    """
    Facebook's other profile shapes, all of them somebody's (or some page's) own:
    `/p/Ім'я-1000…` (the newer address for pages and professional profiles),
    `/people/Ім'я/1000…`, and `/profile.php?id=1000…`. Each of these used to be
    refused as "not the shape of a profile", which threw the person away unread.
    """
    first = segments[0].lower() if segments else ""
    if first == "p" and len(segments) == 2:
        return True
    if first == "people" and len(segments) >= 2:
        return True
    return first == "profile.php" and "id=" in query


def _is_article(segments: list[str]) -> bool:
    """
    A publication rather than a person. Whole segments, plus the year-shaped one
    that dated URLs carry (`/2026/08/…`).
    """
    lowered = [segment.lower() for segment in segments]
    if set(lowered) & ARTICLE_SEGMENTS:
        return True
    return any(part.isdigit() and len(part) == 4 and part.startswith("20") for part in lowered)


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
            page_age=result.page_age,
            age_label=result.age_label,
            language=result.language,
        )
    return list(seen.values())


#: How a post names the account that published it when the address does not: the
#: result title. "Марина Іванова (@marina.mlm) on Instagram: …"
HANDLE_IN_TITLE = re.compile(r"\(@(?P<handle>[a-z0-9._]{2,30})\)", re.IGNORECASE)
HANDLE_BEFORE_PLATFORM = re.compile(
    r"(?:^|[-–—|·•]\s*)(?P<handle>[a-z0-9._]{2,30})\s+on\s+(?:Instagram|Threads)",
    re.IGNORECASE,
)
#: The segment that says "what follows is one piece of content, not an account".
#: `instagram.com/p/Cxyz` puts it first — there is no author in that address at all.
#: `instagram.com/marina.mlm/reel/Cxyz` puts it *second*, and then the segment
#: before it is the author's handle, spelled out by the platform itself.
POST_SEGMENTS = {
    "p",
    "reel",
    "reels",
    "tv",
    "post",
    "posts",
    "videos",
    "video",
    "photos",
    "mentions",
}

#: Handles a platform uses for its own pages. Reading one as a person would send a
#: paid request to a login form.
NOT_A_HANDLE = {
    "accounts",
    "explore",
    "popular",
    "directory",
    "help",
    "about",
    "legal",
    "privacy",
    "policies",
    "pages",
    "groups",
    "events",
    "marketplace",
    "watch",
    "story.php",
    "photo.php",
    "profile.php",
    "permalink.php",
    "share",
    "sharer",
    "login",
    "p",
    "reel",
    "reels",
}

#: How many of one person's posts travel with their profile as evidence. Enough to
#: show what they publish; more is tokens for the judge and nothing new.
MAX_POSTS_PER_AUTHOR = 3

#: `linkedin.com/posts/{vanity}_{words}-activity-{id}-{x}`: the author's public
#: profile name comes before the first underscore. LinkedIn vanity names are
#: letters, digits and hyphens only, so the underscore is an unambiguous separator.
LINKEDIN_POST = re.compile(r"^(?P<vanity>[a-z0-9-]{3,100})_", re.IGNORECASE)
#: What a handle looks like. Not a bare number: `facebook.com/581399108893746` is a
#: page's internal id, and the page it belongs to has no name to judge.
HANDLE_SHAPE = re.compile(r"^(?=.*[a-z])[a-z0-9._-]{3,40}$", re.IGNORECASE)

#: Where a promoted profile lives, per platform.
PROFILE_HOST = {
    Platform.INSTAGRAM: "instagram.com",
    Platform.THREADS: "threads.net",
    Platform.FACEBOOK: "facebook.com",
}


def promote_posts(urls: list[DiscoveredUrl]) -> list[DiscoveredUrl]:
    """
    Turn a post into the person who wrote it.

    Searching a social network for a phrase returns *content* far more often than
    accounts — reels, videos, photos, posts — and `classify` rightly refuses a post
    as a candidate: a post is not a profile. But the author is exactly who the
    search was looking for, and there are two places their name is written down.

    The first is the address, and it is the one that was being ignored. One run
    threw away `instagram.com/yanarogozha/reel/C3Z5y19owoo`,
    `instagram.com/iriska.kononova/reel/DDHwmwvtuTo` and
    `facebook.com/ajzan.balakesova/videos/…` as "not people" — three real people
    whose handle is the first segment of the URL the provider handed us. Anything
    of the form `{handle}/{reel|p|videos|posts|…}/…` names its author out loud.

    The second is the result title, which is where Instagram and Threads put the
    handle when the address does not carry it (`instagram.com/p/Cxyz`).

    Nothing is invented either way: the handle is copied verbatim from the
    provider's own address or text, and the profile URL is the platform's
    documented shape. A handle that turns out not to exist costs one unreadable
    page, which the chain already handles.

    Every post by an author is kept on the author's profile (`posts`), not only
    the first: the posts are what the person publishes, and they are often the
    only evidence of what the search was looking for. The post also records where
    its author is (`author_url`), so the refused list can say who was checked.
    """
    by_canonical = {url.canonical_url: url for url in urls}
    promoted: dict[str, DiscoveredUrl] = {}
    posts_of: dict[str, list[FoundPost]] = {}
    marked: list[DiscoveredUrl] = []

    for url in urls:
        profile = author_profile(url)
        if profile is None:
            marked.append(url)
            continue

        canonical = canonicalize(profile)
        marked.append(url.model_copy(update={"author_url": canonical}))
        posts_of.setdefault(canonical, []).append(_as_post(url))
        if canonical in by_canonical or canonical in promoted:
            continue
        promoted[canonical] = url.model_copy(
            update={
                "url": profile,
                "canonical_url": canonical,
                "kind": UrlKind.CANDIDATE,
                # The post is what was found; the profile is where to look. The
                # post's own text stays attached as the evidence it is.
                "author_url": None,
            }
        )

    def with_posts(url: DiscoveredUrl) -> DiscoveredUrl:
        found = posts_of.get(url.canonical_url)
        if not found:
            return url
        return url.model_copy(update={"posts": _merge_posts(url.posts, found)})

    return [with_posts(url) for url in marked] + [with_posts(url) for url in promoted.values()]


def attach_posts(urls: list[DiscoveredUrl], posts: list[DiscoveredUrl]) -> list[DiscoveredUrl]:
    """
    Fold posts whose author was found later (by opening the post) into the list:
    each post gets its `author_url`, and each author's profile is added — or, if it
    is already there, given the post as evidence.
    """
    resolved = {post.canonical_url: post for post in posts if post.author_url}
    if not resolved:
        return urls

    posts_of: dict[str, list[FoundPost]] = {}
    first_post: dict[str, DiscoveredUrl] = {}
    for post in resolved.values():
        author = post.author_url or ""
        posts_of.setdefault(author, []).append(_as_post(post))
        first_post.setdefault(author, post)

    updated = [
        url.model_copy(update={"author_url": resolved[url.canonical_url].author_url})
        if url.canonical_url in resolved
        else url
        for url in urls
    ]
    present = {url.canonical_url for url in updated}
    for author, post in first_post.items():
        if author not in present:
            updated.append(
                post.model_copy(
                    update={
                        "url": author,
                        "canonical_url": author,
                        "kind": UrlKind.CANDIDATE,
                        "author_url": None,
                        "posts": [],
                    }
                )
            )

    return [
        url.model_copy(update={"posts": _merge_posts(url.posts, posts_of[url.canonical_url])})
        if url.canonical_url in posts_of
        else url
        for url in updated
    ]


def _as_post(url: DiscoveredUrl) -> FoundPost:
    return FoundPost(
        url=url.url,
        title=url.title,
        snippet=url.snippet,
        published_at=url.page_age,
        age_label=url.age_label,
    )


def _merge_posts(existing: list[FoundPost], found: list[FoundPost]) -> list[FoundPost]:
    """One entry per post address, newest first, capped."""
    seen: dict[str, FoundPost] = {}
    for post in [*existing, *found]:
        seen.setdefault(canonicalize(post.url), post)
    ordered = sorted(
        seen.values(),
        key=lambda post: post.published_at.timestamp() if post.published_at else float("-inf"),
        reverse=True,
    )
    return ordered[:MAX_POSTS_PER_AUTHOR]


def needs_opening(url: DiscoveredUrl) -> bool:
    """
    A post whose author neither the address nor the result title names:
    `instagram.com/p/Cxyz`, `instagram.com/reel/Cxyz`. Opening the post is the only
    way to learn who published it — and the post page says so in its first line.
    """
    if url.platform is not Platform.INSTAGRAM or url.author_url or author_profile(url):
        return False
    segments = [segment for segment in urlparse(url.canonical_url).path.split("/") if segment]
    return len(segments) == 2 and segments[0].lower() in {"p", "reel", "reels", "tv"}


def author_profile(url: DiscoveredUrl) -> str | None:
    """
    Where the person who published this post lives, or None if the post does not
    name them.

    Public because the pipeline asks the same question a second time, for a
    different purpose: when it lists the addresses it refused, a post whose author
    *was* followed has to say so, or the list reads as a lost lead when the lead
    is sitting in the other column.
    """
    if url.author_url:
        return url.author_url
    if url.platform is Platform.LINKEDIN:
        return _linkedin_author(url)
    if url.platform is Platform.FACEBOOK:
        by_id = _facebook_story_author(url)
        if by_id:
            return by_id
    host = PROFILE_HOST.get(url.platform)
    if host is None:
        return None
    handle = _author(url)
    if handle is None:
        return None
    prefix = "@" if url.platform is Platform.THREADS else ""
    return f"https://{host}/{prefix}{handle}"


def _linkedin_author(url: DiscoveredUrl) -> str | None:
    """`/posts/{vanity}_…` → `/in/{vanity}`. Other LinkedIn content names nobody."""
    segments = [segment for segment in urlparse(url.canonical_url).path.split("/") if segment]
    if len(segments) < 2 or segments[0].lower() != "posts":
        return None
    match = LINKEDIN_POST.match(unquote(segments[1]))
    if match is None:
        return None
    return f"https://linkedin.com/in/{match.group('vanity').lower()}"


def _facebook_story_author(url: DiscoveredUrl) -> str | None:
    """
    `permalink.php?story_fbid=…&id=1000…` and `story.php?…&id=…`: the `id` is the
    account that published the story, and `profile.php?id=` is where it lives.
    """
    parsed = urlparse(url.canonical_url)
    segments = [segment for segment in parsed.path.split("/") if segment]
    if segments[:1] not in (["permalink.php"], ["story.php"]):
        return None
    owner = dict(parse_qsl(parsed.query)).get("id", "")
    return f"https://facebook.com/profile.php?id={owner}" if owner.isdigit() else None


def _author(url: DiscoveredUrl) -> str | None:
    """The handle that published this post, from the address first and the title after."""
    segments = [segment for segment in urlparse(url.canonical_url).path.split("/") if segment]
    if not segments:
        return None

    # `{handle}/reel/…`, `{handle}/videos/…`: the platform wrote the author down.
    if len(segments) > 1 and segments[1].lower() in POST_SEGMENTS:
        # A Facebook page may be addressed by its number: `/100066734753457/photos/…`
        # is that page's photo, and `/100066734753457` is the page.
        if url.platform is Platform.FACEBOOK and segments[0].isdigit():
            return segments[0]
        return _handle(segments[0])

    # `/p/Cxyz`, `/reel/Cxyz`: one piece of content and no author in the address.
    if segments[0].lower() not in POST_SEGMENTS:
        return None
    if url.platform is Platform.FACEBOOK:
        # Facebook titles name the page, not a handle we could build a URL from.
        return None
    text = " ".join(part for part in (url.title, url.snippet) if part)
    match = HANDLE_IN_TITLE.search(text) or HANDLE_BEFORE_PLATFORM.search(text)
    return _handle(match.group("handle")) if match else None


def _handle(segment: str) -> str | None:
    """A handle we are willing to spend a paid page read on."""
    handle = unquote(segment).strip(".").lstrip("@")
    if handle.casefold() in NOT_A_HANDLE or not HANDLE_SHAPE.match(handle):
        return None
    return handle


def candidates(
    urls: list[DiscoveredUrl], sources: list[SourceKind] | None = None
) -> list[DiscoveredUrl]:
    """
    URLs worth spending an extraction credit on, from the sources that were asked
    for. `unknown` is included on purpose — a personal website rarely looks like a
    profile, and dropping it would lose exactly the leads the public-web-first
    approach is after.

    The source list is a *restriction*, and it is applied here as well as in the
    generated queries, because `site:` is a request rather than a guarantee: a
    provider will still return a news site for a `site:instagram.com` query, and a
    search told to look at three social networks came back with a legal journal's
    article about network marketing. Two places to enforce one instruction is not
    duplication — it is the difference between asking and requiring.

    `unknown` on a *social* platform is a different matter and is dropped: those
    sites name their profiles in one documented shape, so an address that is not
    that shape is a photo, a login form or a directory page — never a person we
    failed to recognise.
    """
    allowed = allowed_platforms(sources)
    return [
        url for url in urls if _worth_reading(url) and (allowed is None or url.platform in allowed)
    ]


def _worth_reading(url: DiscoveredUrl) -> bool:
    if url.kind is UrlKind.CANDIDATE:
        return True
    return url.kind is UrlKind.UNKNOWN and url.platform not in SOCIAL_PLATFORMS


def allowed_platforms(sources: list[SourceKind] | None) -> set[Platform] | None:
    """
    Which platforms these sources cover. `None` means "no restriction", which is
    what an empty source list means: nothing was asked for, so nothing is refused.
    """
    if not sources:
        return None
    allowed: set[Platform] = set()
    for source in sources:
        allowed |= PLATFORMS_BY_SOURCE.get(source, set())
    return allowed or None
