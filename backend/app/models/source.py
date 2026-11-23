"""
Sources and raw provider output (spec §26).

Never store only AI conclusions: a lead keeps the pages it was derived from, so
every claim can be re-checked and the profile can be re-analysed later without
searching again.
"""

from datetime import UTC, datetime
from enum import StrEnum

from pydantic import BaseModel, Field

from app.models.common import Platform


class LeadSourceKind(StrEnum):
    """What a lead's source is: their own page, or something they published."""

    PAGE = "page"
    #: A post, reel or video the person published. Its words are theirs, which is
    #: why it counts as evidence about the person and not as a page about them.
    POST = "post"


class LeadSource(BaseModel):
    """A public page a lead was found on."""

    id: str
    platform: Platform
    url: str
    title: str
    snippet: str
    discovered_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    kind: LeadSourceKind = LeadSourceKind.PAGE
    #: When a post was published, if the index or the post itself said so.
    published_at: datetime | None = None


class ProviderResult(BaseModel):
    """One hit as returned by a SearchProvider, before any interpretation."""

    url: str
    title: str
    snippet: str
    query: str
    provider: str

    #: What the index knows about the page beyond its text. `page_age` is the only
    #: recency evidence available before anything is fetched, which is what makes
    #: an "active" observation possible at all; the fixture provider leaves both
    #: empty, so nothing downstream may assume they are set.
    page_age: datetime | None = None
    age_label: str | None = None
    #: The result's own language tag ("es"), not the query's.
    language: str | None = None


class UrlKind(StrEnum):
    """Classification from CandidateDiscoveryService (spec §32)."""

    CANDIDATE = "candidate"
    COMPANY = "company"
    ARTICLE = "article"
    PRODUCT = "product"
    IRRELEVANT = "irrelevant"
    UNKNOWN = "unknown"


class FoundPost(BaseModel):
    """
    A post the search found, kept on the profile of the person who published it.

    The post is often the only reason the person was found at all — a reel titled
    "Dlaczego network marketing?" — so it travels with the author's profile as
    evidence instead of being thrown away with the post's address.
    """

    url: str
    title: str = ""
    snippet: str = ""
    published_at: datetime | None = None
    age_label: str | None = None


class DiscoveredUrl(BaseModel):
    """A normalized, classified URL — the unit the extraction stage consumes."""

    url: str
    canonical_url: str
    platform: Platform
    kind: UrlKind
    title: str
    snippet: str
    query: str
    provider: str

    page_age: datetime | None = None
    age_label: str | None = None
    language: str | None = None

    #: On a profile: the posts by this person the search found (newest evidence of
    #: what they publish). Empty for everything else.
    posts: list[FoundPost] = Field(default_factory=list)
    #: On a post: the profile of the account that published it, once known — from
    #: the address, the result title, or by opening the post.
    author_url: str | None = None
