"""
Fixture extractor — the Phase 2 stand-in for ScrapeGraphAI.

Looks the URL up in the seeded catalogue and returns that person's structured
profile. URLs it does not recognise return `None`, which is the same answer the
real extractor gives for a blocked or irrelevant page — so the pipeline's
"extracted, but nothing usable" branch is exercised from day one.
"""

from app.models.common import GeoLocation
from app.models.lead import Lead
from app.models.profile import ExtractedProfile
from app.models.source import DiscoveredUrl
from app.services.scraping.base import ProfileExtractor
from app.services.search.url_tools import canonicalize


class FixtureProfileExtractor(ProfileExtractor):
    name = "fixture"

    def __init__(self, catalogue: list[Lead]) -> None:
        self._by_url: dict[str, Lead] = {}
        for lead in catalogue:
            for entry in lead.platforms:
                self._by_url.setdefault(canonicalize(entry.url), lead)
            for source in lead.sources:
                self._by_url.setdefault(canonicalize(source.url), lead)
            if lead.contacts.website:
                self._by_url.setdefault(canonicalize(lead.contacts.website), lead)

    async def extract(self, url: DiscoveredUrl) -> ExtractedProfile | None:
        lead = self._by_url.get(url.canonical_url)
        if lead is None:
            return None

        return ExtractedProfile(
            url=url.url,
            canonical_url=url.canonical_url,
            platform=url.platform,
            name=lead.name,
            headline=lead.headline,
            company=lead.company,
            location=lead.location.model_copy() if lead.location else GeoLocation(),
            languages=list(lead.languages),
            summary=lead.summary,
            platforms=[entry.model_copy() for entry in lead.platforms],
            sources=[source.model_copy() for source in lead.sources],
            contacts=lead.contacts.model_copy(),
            # What the page says about this person, before any judgement.
            observations=[signal.model_copy() for signal in lead.signals],
            extractor=self.name,
        )
