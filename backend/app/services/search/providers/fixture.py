"""
Fixture search provider — the Phase 2 stand-in for Brave (spec §28).

It answers queries out of the seeded candidate catalogue by naive text matching,
which is enough to make the pipeline behave like the real thing:

* the criteria decide who is found — a Spain query surfaces Spanish profiles
* the same person is returned by several queries, so deduplication has work to do
* a share of URLs carry tracking parameters, so normalization has work to do
* every query also returns non-people (a post, a company page, a shop), so
  candidate discovery has to reject something

No network, no keys, deterministic for a given query. Since Phase 4 it is the
fallback rather than the default: it runs when no `BRAVE_SEARCH_API_KEY` is
configured (or `SEARCH_PROVIDER=fixture` asks for it), which keeps the demo — and
the test suite — working without a paid account. `SearchMarket` is ignored: the
catalogue has no index to point at a country.
"""

import hashlib

from app.models.common import Platform
from app.models.lead import Lead
from app.models.source import ProviderResult
from app.services.search.providers.base import SearchMarket, SearchProvider

SITE_PLATFORMS: dict[str, Platform] = {
    "instagram.com": Platform.INSTAGRAM,
    "linkedin.com": Platform.LINKEDIN,
    "facebook.com": Platform.FACEBOOK,
    "threads.net": Platform.THREADS,
}

DECOY_TEMPLATES = (
    "https://www.instagram.com/p/{token}/",
    "https://www.linkedin.com/company/{token}-cosmetics/",
    "https://{token}-beauty.example.com/shop/?utm_source=brave",
    "https://beautyblog.example.com/blog/{token}-network-marketing-2026/",
)


class FixtureSearchProvider(SearchProvider):
    name = "fixture"

    def __init__(self, catalogue: list[Lead], results_per_query: int = 6) -> None:
        self._catalogue = catalogue
        self._results_per_query = results_per_query

    async def search(
        self, query: str, limit: int = 20, *, market: SearchMarket | None = None
    ) -> list[ProviderResult]:
        terms, negatives, platform = _parse(query)

        ranked: list[tuple[int, str, Lead]] = []
        for lead in self._catalogue:
            haystack = _haystack(lead)
            if any(word in haystack for word in negatives):
                continue
            if platform and not _url_for(lead, platform):
                continue
            hits = sum(1 for term in terms if term in haystack)
            ranked.append((hits, lead.name, lead))

        ranked.sort(key=lambda row: (-row[0], row[1]))
        matched = [lead for hits, _, lead in ranked if hits] or [lead for _, _, lead in ranked]

        results: list[ProviderResult] = []
        for lead in matched[: self._results_per_query]:
            url = _url_for(lead, platform) or _primary_url(lead)
            if not url:
                continue
            results.append(
                ProviderResult(
                    # Every third hit arrives with tracking noise, as the real web does.
                    url=f"{url}?utm_source=brave&utm_medium=organic"
                    if _bucket(query + url, 3) == 0
                    else url,
                    title=f"{lead.name} — {lead.headline}",
                    snippet=_snippet(lead),
                    query=query,
                    provider=self.name,
                )
            )

        results.extend(_decoys(query))
        return results[:limit]


def _parse(query: str) -> tuple[list[str], list[str], Platform | None]:
    """Split a generated query into positive terms, negatives and a site filter."""
    terms: list[str] = []
    negatives: list[str] = []
    platform: Platform | None = None

    for token in _tokenize(query):
        if token.startswith("site:"):
            host = token.removeprefix("site:").split("/")[0]
            platform = SITE_PLATFORMS.get(host)
        elif token.startswith("-"):
            cleaned = token.lstrip("-").strip('"').lower()
            if cleaned:
                negatives.append(cleaned)
        else:
            cleaned = token.strip('"').lower()
            if cleaned:
                terms.append(cleaned)
    return terms, negatives, platform


def _tokenize(query: str) -> list[str]:
    """Keep quoted phrases together: `-"beauty salon"` is one token."""
    tokens: list[str] = []
    current = ""
    in_quotes = False
    for char in query:
        if char == '"':
            in_quotes = not in_quotes
            current += char
        elif char.isspace() and not in_quotes:
            if current:
                tokens.append(current)
            current = ""
        else:
            current += char
    if current:
        tokens.append(current)
    return tokens


def _haystack(lead: Lead) -> str:
    location = lead.location
    parts = [
        lead.name,
        lead.headline,
        lead.company or "",
        lead.summary,
        location.country if location else "",
        location.city if location else "",
        location.region if location else "",
        " ".join(lead.languages),
        " ".join(signal.evidence or "" for signal in lead.signals),
    ]
    return " ".join(part for part in parts if part).lower()


def _url_for(lead: Lead, platform: Platform | None) -> str | None:
    if platform is None:
        return None
    return next((entry.url for entry in lead.platforms if entry.platform is platform), None)


def _primary_url(lead: Lead) -> str | None:
    if lead.platforms:
        return lead.platforms[0].url
    return lead.contacts.website


def _snippet(lead: Lead) -> str:
    evidence = next((signal.evidence for signal in lead.signals if signal.evidence), None)
    return (evidence or lead.summary)[:220]


def _decoys(query: str) -> list[ProviderResult]:
    token = hashlib.sha1(query.encode()).hexdigest()[:8]
    picks = (_bucket(query, len(DECOY_TEMPLATES)), _bucket(query + "b", len(DECOY_TEMPLATES)))
    return [
        ProviderResult(
            url=DECOY_TEMPLATES[index].format(token=token),
            title="Beauty & network marketing",
            snippet="Not a personal profile — candidate discovery should drop this.",
            query=query,
            provider="fixture",
        )
        for index in dict.fromkeys(picks)
    ]


def _bucket(text: str, buckets: int) -> int:
    return int(hashlib.sha1(text.encode()).hexdigest(), 16) % buckets
