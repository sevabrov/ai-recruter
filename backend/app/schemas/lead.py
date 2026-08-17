"""Lead API schemas (spec §19, §16, §57)."""

from datetime import datetime

from pydantic import Field

from app.models.common import (
    LeadStatus,
    OutreachChannel,
    OutreachTone,
    Platform,
    SignalType,
)
from app.schemas.common import CamelModel
from app.schemas.search import GeoLocationSchema


class LeadPlatformSchema(CamelModel):
    platform: Platform
    handle: str | None = None
    url: str
    followers: int | None = None


class LeadSignalSchema(CamelModel):
    """Evidence travels with the signal (spec §16) so the UI can show the quote."""

    type: SignalType
    detected: bool
    confidence: float
    evidence: str | None = None
    source_url: str | None = None
    source_platform: Platform | None = None


class LeadSourceSchema(CamelModel):
    id: str
    platform: Platform
    url: str
    title: str
    snippet: str
    discovered_at: datetime


class ScoreComponentSchema(CamelModel):
    type: SignalType
    awarded: int
    max: int


class LeadContactsSchema(CamelModel):
    email: str | None = None
    website: str | None = None
    phone: str | None = None


class LeadNoteSchema(CamelModel):
    id: str
    body: str
    author: str
    created_at: datetime


class LeadOut(CamelModel):
    """
    `user_id` and the internal merge trail are deliberately absent: the browser
    gets what it renders and nothing more.
    """

    id: str
    search_id: str
    search_name: str

    name: str
    headline: str
    company: str | None = None
    location: GeoLocationSchema | None = None
    languages: list[str]

    score: int
    score_breakdown: list[ScoreComponentSchema]

    platforms: list[LeadPlatformSchema]
    summary: str
    signals: list[LeadSignalSchema]
    sources: list[LeadSourceSchema]
    contacts: LeadContactsSchema

    status: LeadStatus
    saved: bool
    archived: bool
    notes: list[LeadNoteSchema]

    created_at: datetime
    updated_at: datetime | None = None


class UpdateLeadIn(CamelModel):
    """`PATCH /leads/:id` — every field optional, only what is sent changes."""

    status: LeadStatus | None = None
    saved: bool | None = None
    archived: bool | None = None


class AddNoteIn(CamelModel):
    body: str = Field(min_length=1, max_length=4000)


class OutreachIn(CamelModel):
    channel: OutreachChannel
    tone: OutreachTone
    language: str = Field(min_length=2, max_length=40)


class OutreachOut(CamelModel):
    id: str
    lead_id: str
    channel: OutreachChannel
    tone: OutreachTone
    language: str
    subject: str | None = None
    body: str
    created_at: datetime


class LeadFacetsOut(CamelModel):
    """Filter options derived from the data actually present."""

    countries: list[str]
    platforms: list[Platform]
