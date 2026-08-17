"""
Extraction interface (spec §33–34).

One method, one URL, one strict schema out. Whether the page was read by
ScrapeGraphAI, a plain HTTP fetch or a fixture is invisible to the pipeline, and
`None` is a legitimate answer: blocked pages, empty pages and pages that turn out
not to describe a person all end here rather than becoming a bad lead.
"""

from typing import Protocol

from app.models.profile import ExtractedProfile
from app.models.source import DiscoveredUrl


class ProfileExtractor(Protocol):
    name: str

    async def extract(self, url: DiscoveredUrl) -> ExtractedProfile | None:
        """Return the structured profile, or None if the page yields nothing usable."""
        ...
