"""
Lead filter query parameters.

Snake_case on purpose: this is what the frontend client sends
(`frontend/src/services/api/api-services.ts`) and what reads naturally in a URL.
Repeatable parameters (`?country=Spain&country=Italy`) collect into lists.

`search_id` is split out into its own dependency because on
`/searches/{search_id}/leads` that name is already a path parameter — there the
scope comes from the path, not the query string.
"""

from typing import Annotated

from fastapi import Depends, Query

from app.models.common import LeadSort, LeadStatus, Platform, SignalType
from app.models.query import LeadQuery


def lead_filters(
    q: Annotated[str | None, Query(max_length=200)] = None,
    min_score: Annotated[int | None, Query(ge=0, le=100)] = None,
    country: Annotated[list[str] | None, Query()] = None,
    platform: Annotated[list[Platform] | None, Query()] = None,
    signal: Annotated[list[SignalType] | None, Query()] = None,
    status: Annotated[list[LeadStatus] | None, Query()] = None,
    has_email: Annotated[bool, Query()] = False,
    has_social: Annotated[bool, Query()] = False,
    saved: Annotated[bool, Query()] = False,
    include_archived: Annotated[bool, Query()] = False,
    sort: Annotated[LeadSort, Query()] = LeadSort.SCORE_DESC,
    page: Annotated[int, Query(ge=1)] = 1,
    # The Leads screen asks for the whole workspace in one go; the ceiling is
    # here to bound a hostile request, not to constrain the UI.
    page_size: Annotated[int, Query(ge=1, le=500)] = 50,
) -> LeadQuery:
    return LeadQuery(
        query=q,
        min_score=min_score,
        countries=country or [],
        platforms=platform or [],
        signals=signal or [],
        statuses=status or [],
        has_email=has_email,
        has_social=has_social,
        saved_only=saved,
        include_archived=include_archived,
        sort=sort,
        page=page,
        page_size=page_size,
    )


LeadFiltersDep = Annotated[LeadQuery, Depends(lead_filters)]


def lead_query(
    filters: LeadFiltersDep,
    search_id: Annotated[str | None, Query()] = None,
) -> LeadQuery:
    return filters.model_copy(update={"search_id": search_id})


LeadQueryDep = Annotated[LeadQuery, Depends(lead_query)]
