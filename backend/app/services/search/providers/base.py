"""
Search provider interface (spec §27, §46–48).

Nothing above this line may know whether results came from Brave, ScrapeGraphAI's
search, or a fixture. That is the whole point: the provider is swappable by
configuration, fallbacks are possible, and Google/Bing stay optional extras that
the application never depends on.
"""

from typing import Protocol

from app.models.source import ProviderResult


class SearchProvider(Protocol):
    #: Reported in `GeneratedQuery.provider` so the UI can show where hits came from.
    name: str

    async def search(self, query: str, limit: int = 20) -> list[ProviderResult]:
        """Run one query. Raises ProviderError once retries are exhausted."""
        ...
