"""
ScrapeGraphAI extractor (spec §33–34) — Phase 5.

A declared seam, like the Brave provider: Phase 2 calls no external service. When
Phase 5 starts, this file gets a body and the registry stops handing out the
fixture extractor.

    from scrapegraph_py import Client
    client = Client(api_key=settings.scrapegraph_api_key)
    client.smartscraper(website_url=url.canonical_url, user_prompt=…,
                        output_schema=ExtractedProfile)

`ExtractedProfile` is already the strict output schema the spec asks for, so the
model is never given room to answer in prose. Things to keep in mind there:
credits are money (§54), pages must not be scraped twice (§53 — cache by
canonical URL + content hash), and not every social URL can be read at all (§60,
Milestone 5) — record which platforms actually work.
"""

from app.core.errors import ProviderError
from app.models.profile import ExtractedProfile
from app.models.source import DiscoveredUrl
from app.services.scraping.base import ProfileExtractor


class ScrapeGraphProfileExtractor(ProfileExtractor):
    name = "scrapegraph"

    def __init__(self, api_key: str) -> None:
        self.api_key = api_key

    async def extract(self, url: DiscoveredUrl) -> ExtractedProfile | None:
        raise ProviderError(
            "ScrapeGraphAI extraction is wired up in Phase 5. Set SCRAPEGRAPH_API_KEY "
            "and implement ScrapeGraphProfileExtractor.extract.",
            provider=self.name,
        )
