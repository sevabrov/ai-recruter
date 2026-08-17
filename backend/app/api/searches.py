"""
Search endpoints (spec §57).

    POST   /searches            create + enqueue, returns immediately (§39)
    GET    /searches            history
    GET    /searches/:id        status and progress — the polling target (§43)
    GET    /searches/:id/leads  results, filterable
    POST   /searches/:id/cancel stop a running search

`response_model_exclude_none` keeps optional fields absent rather than `null`,
which is what the TypeScript contract's `field?:` means.
"""

from fastapi import APIRouter, status

from app.api.deps import ContainerDep, UserDep
from app.api.params import LeadFiltersDep
from app.models.search import SearchCriteria
from app.schemas.common import Paginated
from app.schemas.lead import LeadOut
from app.schemas.search import (
    CreateSearchIn,
    CreateSearchResponse,
    SearchOut,
    SearchSummaryOut,
)

router = APIRouter(prefix="/searches", tags=["searches"])


@router.post(
    "",
    response_model=CreateSearchResponse,
    status_code=status.HTTP_202_ACCEPTED,
    response_model_exclude_none=True,
)
async def create_search(
    payload: CreateSearchIn,
    container: ContainerDep,
    user_id: UserDep,
) -> CreateSearchResponse:
    criteria = SearchCriteria(**payload.to_criteria_kwargs())
    search = await container.searches.create(user_id, payload.name, criteria)
    return CreateSearchResponse(search_id=search.id, status=search.status)


@router.get("", response_model=list[SearchSummaryOut], response_model_exclude_none=True)
async def list_searches(container: ContainerDep, user_id: UserDep) -> list[SearchSummaryOut]:
    searches = await container.searches.list(user_id)
    return [SearchSummaryOut.model_validate(search) for search in searches]


@router.get("/{search_id}", response_model=SearchOut, response_model_exclude_none=True)
async def get_search(search_id: str, container: ContainerDep, user_id: UserDep) -> SearchOut:
    return SearchOut.model_validate(await container.searches.get(user_id, search_id))


@router.get(
    "/{search_id}/leads",
    response_model=Paginated[LeadOut],
    response_model_exclude_none=True,
)
async def search_leads(
    search_id: str,
    filters: LeadFiltersDep,
    container: ContainerDep,
    user_id: UserDep,
) -> Paginated[LeadOut]:
    # Ownership of the search is checked before its leads are listed.
    await container.searches.get(user_id, search_id)
    page = await container.leads.list(user_id, filters.model_copy(update={"search_id": search_id}))
    return Paginated[LeadOut](
        items=[LeadOut.model_validate(lead) for lead in page.items],
        total=page.total,
        page=page.page,
        page_size=page.page_size,
    )


@router.post("/{search_id}/cancel", response_model=SearchOut, response_model_exclude_none=True)
async def cancel_search(search_id: str, container: ContainerDep, user_id: UserDep) -> SearchOut:
    return SearchOut.model_validate(await container.searches.cancel(user_id, search_id))
