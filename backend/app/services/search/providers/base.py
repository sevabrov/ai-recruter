"""
Search provider interface (spec §27, §46–48).

Nothing above this line may know whether results came from Brave, ScrapeGraphAI's
search, or a fixture. That is the whole point: the provider is swappable by
configuration, fallbacks are possible, and Google/Bing stay optional extras that
the application never depends on.

`SearchMarket` is the one thing the interface adds to "a query and a limit": which
country's index to search, and optionally which language. It is expressed in codes
rather than names because that is what an API takes; the mapping from the wizard's
"Spain" lives in `services/search/markets.py`.
"""

from typing import Protocol

from pydantic import BaseModel

from app.models.search import SearchCriteria
from app.models.source import ProviderResult
from app.services.search.markets import country_code, language_code


class SearchMarket(BaseModel):
    country: str | None = None
    language: str | None = None

    @classmethod
    def from_criteria(cls, criteria: SearchCriteria) -> "SearchMarket":
        """
        The country is always worth sending. The language only when the user asked
        for exactly one: "Spanish, English, Russian" means *any* of the three, and
        pinning the index to one of them would hide the other two.
        """
        languages = [code for code in map(language_code, criteria.languages) if code]
        return cls(
            country=country_code(criteria.location.country),
            language=languages[0] if len(languages) == 1 else None,
        )

    @property
    def is_empty(self) -> bool:
        return not (self.country or self.language)


class SearchProvider(Protocol):
    #: Reported in `GeneratedQuery.provider` so the UI can show where hits came from.
    name: str

    async def search(
        self, query: str, limit: int = 20, *, market: SearchMarket | None = None
    ) -> list[ProviderResult]:
        """Run one query. Raises ProviderError once retries are exhausted."""
        ...

    async def aclose(self) -> None:
        """Release whatever the provider holds open (a connection pool, usually)."""
        ...
