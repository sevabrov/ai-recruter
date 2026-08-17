"""
Extracted profile (spec §34).

The strict schema every extractor must fill. Free-form model output is not
allowed: if a field cannot be found it stays `None`, so "we did not find it" and
"it is not true" never collapse into the same value.

`observations` are raw sightings — what the page appears to say about a person.
They become scored signals only after the signal detector has judged them
against the search criteria.
"""

from pydantic import BaseModel, Field

from app.models.common import GeoLocation, Platform
from app.models.lead import LeadContacts, LeadPlatform, LeadSignal
from app.models.source import LeadSource


class ExtractedProfile(BaseModel):
    url: str
    canonical_url: str
    platform: Platform

    name: str | None = None
    headline: str | None = None
    company: str | None = None
    location: GeoLocation = Field(default_factory=GeoLocation)
    languages: list[str] = Field(default_factory=list)
    summary: str | None = None

    platforms: list[LeadPlatform] = Field(default_factory=list)
    sources: list[LeadSource] = Field(default_factory=list)
    contacts: LeadContacts = Field(default_factory=LeadContacts)

    observations: list[LeadSignal] = Field(default_factory=list)

    #: Which adapter produced this, for debugging and cost attribution.
    extractor: str = "unknown"

    @property
    def is_person(self) -> bool:
        """A page without a name is not a lead, whatever else it contains."""
        return bool(self.name)
