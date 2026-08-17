"""
Query generation (spec §29).

One set of criteria is never one query. Deterministic templates only — no LLM,
per the spec — which also means the generated set is reproducible and reviewable:
the wizard's preview and what the worker actually fires are the same strings.

`AIQueryGenerator` can later implement the same interface behind a flag.
"""

from typing import Protocol

from app.models.common import SourceKind
from app.models.search import SearchCriteria

SITE_BY_SOURCE: dict[SourceKind, str] = {
    SourceKind.INSTAGRAM_PUBLIC: "site:instagram.com",
    SourceKind.LINKEDIN_PUBLIC: "site:linkedin.com/in",
    SourceKind.FACEBOOK_PUBLIC: "site:facebook.com",
    SourceKind.THREADS_PUBLIC: "site:threads.net",
}


class QueryGenerator(Protocol):
    def generate(self, criteria: SearchCriteria, limit: int = 12) -> list[str]: ...


class TemplateQueryGenerator(QueryGenerator):
    def generate(self, criteria: SearchCriteria, limit: int = 12) -> list[str]:
        place = self._place(criteria)
        keywords = criteria.keywords or ["network marketing"]
        industries = criteria.industry or ["beauty"]
        business_types = criteria.business_types or ["network marketing"]

        queries: list[str] = []

        def push(*parts: str | None) -> None:
            query = " ".join(part for part in parts if part).strip()
            query = " ".join(query.split())
            if query and query not in queries:
                queries.append(query)

        # Per-source site: queries — the cheapest way to reach public profiles.
        for source in criteria.sources:
            site = SITE_BY_SOURCE.get(source)
            if not site:
                continue
            push(site, f'"{keywords[0]}"', place)
            if len(keywords) > 1:
                push(site, f'"{keywords[1]}"', industries[0], place)

        # Open-web phrasings that catch personal sites and directories.
        push(f'"{keywords[0]} distributor"', place)
        push(f'"{industries[0]} team leader"', f'"{business_types[0]}"', place)
        push(f'"{business_types[0]}"', industries[0], place, "leader")

        if SourceKind.COMPANY_WEBSITES in criteria.sources:
            push(f'"{keywords[0]}"', "distributor", place, "-shop", "-tienda")
        if SourceKind.BLOGS in criteria.sources:
            push(f'"{industries[0]}"', f'"{business_types[0]}"', "blog", place)

        negatives = " ".join(f'-"{word}"' for word in criteria.negative_keywords[:2])
        return [f"{query} {negatives}".strip() if negatives else query for query in queries[:limit]]

    @staticmethod
    def _place(criteria: SearchCriteria) -> str:
        location = criteria.location
        if location.city:
            return f"{location.city} {location.country or ''}".strip()
        return location.country or ""
