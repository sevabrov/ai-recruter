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
