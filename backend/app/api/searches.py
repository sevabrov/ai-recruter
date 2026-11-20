"""
Search endpoints (spec §57).

    POST   /searches               create + enqueue, returns immediately (§39)
    POST   /searches/parse         the client's free-text brief, read into criteria
    POST   /searches/estimate      price a search and preview its queries
    GET    /searches               history
    GET    /searches/:id           status and progress — the polling target (§43)
    GET    /searches/:id/leads     results, filterable
    GET    /searches/:id/rejected  the candidates that were turned away, and why
    POST   /searches/:id/cancel    stop a running search

`response_model_exclude_none` keeps optional fields absent rather than `null`,
which is what the TypeScript contract's `field?:` means.
"""

from fastapi import APIRouter, Query, status

from app.api.deps import ContainerDep, UserDep
from app.api.params import LeadFiltersDep
from app.models.rejection import UNSEEN_REASONS, RejectionReason
from app.models.search import SearchCriteria
from app.schemas.common import Paginated
from app.schemas.lead import LeadOut
from app.schemas.search import (
    CreateSearchIn,
    CreateSearchResponse,
    EstimateIn,
    EstimateOut,
    EstimateWarningOut,
    ParseBriefIn,
    ParseBriefOut,
    QueryPreviewOut,
    RejectedCandidateOut,
    RejectedOut,
    SearchCriteriaSchema,
    SearchOut,
    SearchSummaryOut,
)
from app.services.adapters import use_llm_signals, use_page_reading
from app.services.search.estimate import estimate

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


@router.post("/parse", response_model=ParseBriefOut)
async def parse_brief(payload: ParseBriefIn, container: ContainerDep) -> ParseBriefOut:
    """
    The client's description of a search, read into criteria.

    Nothing is created and nothing is searched: this fills in the review screen,
    where the client sees what was understood and is asked for what was not.
    Never fails for want of a model — the rules read what they can instead.
    """
    parsed = await container.brief_parser.parse(payload.text, payload.locale)
    return ParseBriefOut(
        name=parsed.name,
        criteria=SearchCriteriaSchema.model_validate(parsed.criteria.model_dump()),
        parser=parsed.parser,
    )


@router.post("/estimate", response_model=EstimateOut)
async def estimate_search(payload: EstimateIn, container: ContainerDep) -> EstimateOut:
    """
    What this search would cost, and the exact queries it would run.

    Nothing is created and nothing is spent: this is the wizard's last screen
    asking the backend the two questions the client said they need answered
    before pressing start — how many leads am I asking for, and what does that
    cost. The queries come from the generator the worker uses, so the preview
    cannot drift from the run the way a re-implementation in the browser did.
    """
    settings = container.settings
    criteria = SearchCriteria.model_validate(payload.criteria.model_dump())
    reads_pages = use_page_reading(settings)
    quote = estimate(
        criteria,
        settings,
        generator=container.query_generator,
        reads_pages=reads_pages,
        paid_detector=use_llm_signals(settings),
    )
    return EstimateOut(
        queries=[
            QueryPreviewOut(query=plan.query, language=plan.language) for plan in quote.queries
        ],
        search_calls=quote.search_calls,
        max_pages=quote.max_pages,
        credits=quote.credits,
        target_leads=quote.target_leads,
        pages_per_lead=quote.pages_per_lead,
        max_cost_eur=quote.max_cost_eur,
        reads_pages=reads_pages,
        warnings=[
            EstimateWarningOut(code=note.code, params=note.params) for note in quote.warnings
        ],
    )


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


@router.get("/{search_id}/rejected", response_model=RejectedOut)
async def search_rejected(
    search_id: str,
    container: ContainerDep,
    user_id: UserDep,
    reason: RejectionReason | None = None,
    limit: int = Query(default=500, ge=1, le=2000),
) -> RejectedOut:
    """
    The candidates this search turned away, and why.

    The counterpart to `/leads`, and the answer to the only question a thin result
    really raises: *are we losing people in there?* Every discovered address is in
    exactly one of the two lists, so the pair is a complete account of the run —
    and each refusal carries the address, so any one of them can be opened and
    checked rather than believed.
    """
    await container.searches.get(user_id, search_id)
    items, counts = await container.repository.list_rejections(
        search_id, reason=reason, limit=limit
    )
    return RejectedOut(
        items=[RejectedCandidateOut.model_validate(entry) for entry in items],
        total=sum(counts.values()),
        by_reason=counts,
        unseen=sum(total for key, total in counts.items() if key in UNSEEN_REASONS),
    )


@router.post("/{search_id}/cancel", response_model=SearchOut, response_model_exclude_none=True)
async def cancel_search(search_id: str, container: ContainerDep, user_id: UserDep) -> SearchOut:
    return SearchOut.model_validate(await container.searches.cancel(user_id, search_id))
