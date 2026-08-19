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


class LeadSource(BaseModel):
    """A public page a lead was found on."""

    id: str
    platform: Platform
    url: str
    title: str
    snippet: str
    discovered_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


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
