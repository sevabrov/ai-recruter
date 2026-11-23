"""
A person's own posts, as evidence about the person.

A search for a phrase finds content far more often than accounts, and the
pipeline follows each post to its author (`url_tools.promote_posts`). What it
used to lose on the way was the post itself: the author's profile was read, the
bio replaced the post's text, and the judge decided "mlm" on a bio that said
"Rozwój • Nawyki • Zdrowie" while the reel that found the person was titled
"Czym jest network marketing?". And "active recently" was decided on a profile
page that carries no dates at all, while the post the search found had one.

So the posts travel with the profile: each becomes a source of kind `post`,
labelled as the person's own words for the judge, and a dated one is the
activity sighting it plainly is. Nothing is invented — the post's text and date
are what the search provider (or the post page) returned.
"""

import hashlib
from datetime import UTC, datetime

from app.models.common import SignalType
from app.models.lead import LeadSignal
from app.models.profile import ExtractedProfile
from app.models.source import DiscoveredUrl, FoundPost, LeadSource, LeadSourceKind
from app.services.extraction.vocabulary import ACTIVE_WITHIN_DAYS

#: A post's date is better evidence than a page age (it is when *they* published),
#: and it stays below anything the judge may award from the text itself.
POST_ACTIVITY_CONFIDENCE = 0.6


def with_posts(profile: ExtractedProfile, url: DiscoveredUrl) -> ExtractedProfile:
    """The profile, with the posts the search found by this person attached."""
    if not url.posts:
        return profile

    as_posts = {(post.title, post.snippet) for post in url.posts}
    # The reader copied the first post's search result onto the profile as its
    # source; it is the post, so it is replaced by the post's own entry.
    pages = [
        source
        for source in profile.sources
        if source.kind is LeadSourceKind.POST or (source.title, source.snippet) not in as_posts
    ]
    known = {source.url for source in pages}
    posts = [_source(post, url) for post in url.posts if post.url not in known]
    return profile.model_copy(
        update={
            "sources": [*pages, *posts],
            "observations": _with_activity(profile.observations, url),
        }
    )


def _source(post: FoundPost, url: DiscoveredUrl) -> LeadSource:
    return LeadSource(
        id=f"src_{hashlib.sha1(post.url.encode()).hexdigest()[:10]}",
        platform=url.platform,
        url=post.url,
        title=post.title,
        snippet=post.snippet,
        kind=LeadSourceKind.POST,
        published_at=post.published_at,
    )


def _with_activity(observations: list[LeadSignal], url: DiscoveredUrl) -> list[LeadSignal]:
    """A post published within the activity window is the activity sighting."""
    recent = _newest_recent(url.posts)
    if recent is None:
        return observations

    when = recent.published_at.date().isoformat()  # type: ignore[union-attr]
    title = " ".join((recent.title or recent.snippet or "").split())[:120]
    evidence = f"Published a post on {when}"
    sighting = LeadSignal(
        type=SignalType.ACTIVITY,
        detected=True,
        confidence=POST_ACTIVITY_CONFIDENCE,
        evidence=f"{evidence}: “{title}”" if title else evidence,
        source_url=recent.url,
        source_platform=url.platform,
    )
    replaced = False
    updated: list[LeadSignal] = []
    for observation in observations:
        if str(observation.type) != SignalType.ACTIVITY:
            updated.append(observation)
            continue
        replaced = True
        stronger = observation.detected and observation.confidence > sighting.confidence
        updated.append(observation if stronger else sighting)
    if not replaced:
        updated.append(sighting)
    return updated


def _newest_recent(posts: list[FoundPost]) -> FoundPost | None:
    now = datetime.now(UTC)
    dated = [
        post
        for post in posts
        if post.published_at is not None
        and (now - _aware(post.published_at)).days <= ACTIVE_WITHIN_DAYS
    ]
    return max(dated, key=lambda post: _aware(post.published_at), default=None)  # type: ignore[arg-type]


def _aware(moment: datetime) -> datetime:
    return moment if moment.tzinfo else moment.replace(tzinfo=UTC)
