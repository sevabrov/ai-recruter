"""
Brave Search provider (spec §28) — Phase 4.

Left as a declared seam on purpose: Phase 2 must not call external services. The
work when Phase 4 starts is this file and nothing else, because the pipeline
already talks to `SearchProvider`.

    GET https://api.search.brave.com/res/v1/web/search
        ?q=<query>&count=<limit>&result_filter=web
        X-Subscription-Token: settings.brave_search_api_key

    → data["web"]["results"][] → {url, title, description}

Notes for that phase: the key is server-side only (§55); every call is wrapped in
`retry_async` (§51); concurrency is capped by SEARCH_CONCURRENCY (§52); and
`SearchUsage.search_api_calls` must be incremented per call (§54).
"""

from app.core.errors import ProviderError
from app.models.source import ProviderResult
from app.services.search.providers.base import SearchProvider


class BraveSearchProvider(SearchProvider):
    name = "brave"

    def __init__(self, api_key: str) -> None:
        self.api_key = api_key

    async def search(self, query: str, limit: int = 20) -> list[ProviderResult]:
        raise ProviderError(
            "Brave Search is wired up in Phase 4. Set BRAVE_SEARCH_API_KEY and "
            "implement BraveSearchProvider.search to enable live web search.",
            provider=self.name,
        )
