"""
`GET /sources` — what reading the web actually yields, per platform.

Milestone 5 says it twice: *"Record which sources consistently provide usable
content"* and *"Do not assume every social-network URL can be scraped."* This is
that record. It is computed from the scrape cache, which means it is the history of
this workspace's own attempts: every page read, with what came back.

Operationally it answers the question the demo cannot: when a live search returns
fewer leads than expected, is that the criteria, or is Instagram showing us a login
wall? One is a search to refine, the other is a source to stop counting on.
"""

from fastapi import APIRouter

from app.api.deps import ContainerDep
from app.schemas.sources import SourceReliabilityOut, SourcesOut
from app.services.adapters import stage_modes, use_page_reading

router = APIRouter(prefix="/sources", tags=["sources"])


@router.get("", response_model=SourcesOut)
async def sources(container: ContainerDep) -> SourcesOut:
    settings = container.settings
    reading = use_page_reading(settings)
    records = await container.repository.source_reliability()

    return SourcesOut(
        reader=stage_modes(settings)["extraction"],
        live=reading,
        cache_ttl_hours=settings.scrape_cache_ttl_hours,
        fallback=_fallback(settings, reading),
        items=[
            SourceReliabilityOut(
                platform=record.platform,
                pages=record.pages,
                usable=record.usable,
                not_a_person=record.not_a_person,
                empty=record.empty,
                blocked=record.blocked,
                failed=record.failed,
                usable_share=record.usable_share,
                last_read_at=record.last_read_at,
            )
            for record in records
        ],
    )


def _fallback(settings, reading: bool) -> str:
    if not reading:
        return "No page is fetched: profiles come from the search results themselves."
    if settings.scrapegraph_fallback_to_snippets:
        return "A page that will not open falls back to the search result it came from."
    return "A page that will not open is dropped."
