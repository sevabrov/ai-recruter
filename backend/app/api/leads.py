"""
Lead endpoints (spec §57, §17).

    GET    /leads              filter, sort, paginate
    GET    /leads/facets       available countries and platforms
    GET    /leads/:id
    PATCH  /leads/:id          status / saved / archived
    POST   /leads/:id/save     §57's explicit save…
    DELETE /leads/:id/save     …and unsave — both thin wrappers over PATCH
    POST   /leads/:id/notes
    POST   /leads/:id/outreach draft a message

`/leads/facets` is declared before `/leads/{lead_id}`; otherwise "facets" would
be read as a lead id.
"""

from fastapi import APIRouter

from app.api.deps import ContainerDep, UserDep
from app.api.params import LeadQueryDep
from app.schemas.common import Paginated
from app.schemas.lead import (
    AddNoteIn,
    LeadFacetsOut,
    LeadOut,
    OutreachIn,
    OutreachOut,
    UpdateLeadIn,
)

router = APIRouter(prefix="/leads", tags=["leads"])


@router.get("", response_model=Paginated[LeadOut], response_model_exclude_none=True)
async def list_leads(
    query: LeadQueryDep,
    container: ContainerDep,
    user_id: UserDep,
) -> Paginated[LeadOut]:
    page = await container.leads.list(user_id, query)
    return Paginated[LeadOut](
        items=[LeadOut.model_validate(lead) for lead in page.items],
        total=page.total,
        page=page.page,
        page_size=page.page_size,
    )


@router.get("/facets", response_model=LeadFacetsOut)
async def lead_facets(container: ContainerDep, user_id: UserDep) -> LeadFacetsOut:
    countries, platforms = await container.leads.facets(user_id)
    return LeadFacetsOut(countries=countries, platforms=platforms)


@router.get("/{lead_id}", response_model=LeadOut, response_model_exclude_none=True)
async def get_lead(lead_id: str, container: ContainerDep, user_id: UserDep) -> LeadOut:
    return LeadOut.model_validate(await container.leads.get(user_id, lead_id))


@router.patch("/{lead_id}", response_model=LeadOut, response_model_exclude_none=True)
async def update_lead(
    lead_id: str,
    payload: UpdateLeadIn,
    container: ContainerDep,
    user_id: UserDep,
) -> LeadOut:
    lead = await container.leads.update(
        user_id,
        lead_id,
        status=payload.status,
        saved=payload.saved,
        archived=payload.archived,
    )
    return LeadOut.model_validate(lead)


@router.post("/{lead_id}/save", response_model=LeadOut, response_model_exclude_none=True)
async def save_lead(lead_id: str, container: ContainerDep, user_id: UserDep) -> LeadOut:
    return LeadOut.model_validate(await container.leads.update(user_id, lead_id, saved=True))


@router.delete("/{lead_id}/save", response_model=LeadOut, response_model_exclude_none=True)
async def unsave_lead(lead_id: str, container: ContainerDep, user_id: UserDep) -> LeadOut:
    return LeadOut.model_validate(await container.leads.update(user_id, lead_id, saved=False))


@router.post("/{lead_id}/notes", response_model=LeadOut, response_model_exclude_none=True)
async def add_note(
    lead_id: str,
    payload: AddNoteIn,
    container: ContainerDep,
    user_id: UserDep,
) -> LeadOut:
    return LeadOut.model_validate(await container.leads.add_note(user_id, lead_id, payload.body))


@router.post("/{lead_id}/outreach", response_model=OutreachOut)
async def draft_outreach(
    lead_id: str,
    payload: OutreachIn,
    container: ContainerDep,
    user_id: UserDep,
) -> OutreachOut:
    lead = await container.leads.get(user_id, lead_id)
    message = container.outreach.draft(
        lead,
        channel=payload.channel,
        tone=payload.tone,
        language=payload.language,
    )
    return OutreachOut.model_validate(message)
