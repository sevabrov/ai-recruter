"""
Lead domain model (spec §25, §16).

Field names are shared with the API schemas one-for-one, so the mapping between
this layer and `schemas/lead.py` stays a rename-free `model_validate`. In Phase 3
these classes become SQLAlchemy models with the same columns.
"""

from datetime import UTC, datetime

from pydantic import BaseModel, Field

from app.models.common import (
    GeoLocation,
    LeadStatus,
    OutreachChannel,
    OutreachTone,
    Platform,
    SignalType,
)
from app.models.source import LeadSource


class LeadPlatform(BaseModel):
    platform: Platform
    handle: str | None = None
    url: str
    followers: int | None = None


class LeadSignal(BaseModel):
    """
    Never a bare boolean (spec §16): a signal carries how sure we are, the quote
    that convinced us and where that quote came from.
    """

    type: SignalType
    detected: bool
    confidence: float = Field(ge=0, le=1)
    evidence: str | None = None
    source_url: str | None = None
    source_platform: Platform | None = None


class ScoreComponent(BaseModel):
    """One row of the explainable breakdown (spec §38): `+18 of 20 Recruiting`."""

    type: SignalType
    awarded: int
    max: int


class LeadContacts(BaseModel):
    email: str | None = None
    website: str | None = None
    phone: str | None = None


class LeadNote(BaseModel):
    id: str
    body: str
    author: str
    created_at: datetime


class Lead(BaseModel):
    id: str
    # Ownership lives on the entity but never leaves the API layer (spec §55).
    user_id: str
    search_id: str
    search_name: str

    name: str
    headline: str
    company: str | None = None
    location: GeoLocation | None = None
    languages: list[str] = Field(default_factory=list)

    score: int
    score_breakdown: list[ScoreComponent] = Field(default_factory=list)

    platforms: list[LeadPlatform] = Field(default_factory=list)
    summary: str
    signals: list[LeadSignal] = Field(default_factory=list)
    sources: list[LeadSource] = Field(default_factory=list)
    contacts: LeadContacts = Field(default_factory=LeadContacts)

    status: LeadStatus = LeadStatus.NEW
    saved: bool = False
    archived: bool = False
    notes: list[LeadNote] = Field(default_factory=list)

    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime | None = None

    #: Canonical URLs this person was merged from (spec §45).
    merged_urls: list[str] = Field(default_factory=list)

    def detected_signals(self) -> set[SignalType]:
        return {signal.type for signal in self.signals if signal.detected}


class OutreachMessage(BaseModel):
    id: str
    lead_id: str
    channel: OutreachChannel
    tone: OutreachTone
    language: str
    subject: str | None = None
    body: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
