"""
What a caller may ask the store for.

This lives in `models/` rather than in the lead service because both sides of the
storage seam speak it now: the API builds a `LeadQuery` from query parameters and
the repository turns it into WHERE / ORDER BY / LIMIT. Keeping it here is what
stops `app/db/` from importing `app/services/`.
"""

from pydantic import BaseModel, Field

from app.models.common import LeadSort, LeadStatus, Platform, SignalType
from app.models.lead import Lead


class LeadQuery(BaseModel):
    """Everything the results and Leads screens can ask for (spec §14, §17)."""

    search_id: str | None = None
    query: str | None = None
    min_score: int | None = None
    countries: list[str] = Field(default_factory=list)
    platforms: list[Platform] = Field(default_factory=list)
    signals: list[SignalType] = Field(default_factory=list)
    statuses: list[LeadStatus] = Field(default_factory=list)
    has_email: bool = False
    has_social: bool = False
    saved_only: bool = False
    include_archived: bool = False
    sort: LeadSort = LeadSort.SCORE_DESC
    page: int = 1
    page_size: int = 50


class Page(BaseModel):
    items: list[Lead]
    total: int
    page: int
    page_size: int


class LeadStats(BaseModel):
    """Counts the dashboard needs, computed by the database rather than in Python."""

    total: int = 0
    high_quality: int = 0
    saved: int = 0
