"""
Lead service (spec §14, §17, §57).

Filtering, sorting and pagination happen here rather than in the repository
because the Phase 2 store cannot push predicates down. The signatures are chosen
so Phase 3 can translate `LeadQuery` straight into SQL: every field is a WHERE
clause, `sort` is ORDER BY, `page`/`page_size` are LIMIT/OFFSET.
"""

# `list` is a method name here, so annotations must stay lazy to keep the builtin.
from __future__ import annotations

import hashlib
from datetime import UTC, datetime

from pydantic import BaseModel, Field

from app.core.errors import NotFoundError
from app.db.repository import Repository
from app.models.common import (
    SOCIAL_PLATFORMS,
    LeadSort,
    LeadStatus,
    Platform,
    SignalType,
)
from app.models.lead import Lead, LeadNote


class LeadQuery(BaseModel):
    """Everything the results and Leads screens can ask for."""

    search_id: str | None = None
    query: str | None = None
    min_score: int | None = None
    countries: list[str] = Field(default_factory=list)
    platforms: list[Platform] = Field(default_factory=list)
    signals: list[SignalType] = Field(default_factory=list)
    statuses: list[LeadStatus] = Field(default_factory=list)
    has_email: bool = False
    has_social: bool = False
    saved_only: bool = False
    include_archived: bool = False
    sort: LeadSort = LeadSort.SCORE_DESC
    page: int = 1
    page_size: int = 50


class Page(BaseModel):
    items: list[Lead]
    total: int
    page: int
    page_size: int


class LeadService:
    def __init__(self, repository: Repository) -> None:
        self.repo = repository

    async def list(self, user_id: str, query: LeadQuery) -> Page:
        leads = await self.repo.list_leads(user_id)
        matched = _sort(_filter(leads, query), query.sort)
        start = max(0, (query.page - 1) * query.page_size)
        return Page(
            items=matched[start : start + query.page_size],
            total=len(matched),
            page=query.page,
            page_size=query.page_size,
        )

    async def get(self, user_id: str, lead_id: str) -> Lead:
        lead = await self.repo.get_lead(lead_id)
        if lead is None or lead.user_id != user_id:
            raise NotFoundError(f"Lead {lead_id} not found", lead_id=lead_id)
        return lead

    async def update(
        self,
        user_id: str,
        lead_id: str,
        *,
        status: LeadStatus | None = None,
        saved: bool | None = None,
        archived: bool | None = None,
    ) -> Lead:
        lead = await self.get(user_id, lead_id)
        updates: dict[str, object] = {"updated_at": datetime.now(UTC)}
        if status is not None:
            updates["status"] = status
        if saved is not None:
            updates["saved"] = saved
        if archived is not None:
            updates["archived"] = archived

        updated = lead.model_copy(update=updates)
        await self.repo.save_lead(updated)
        return updated

    async def add_note(self, user_id: str, lead_id: str, body: str, author: str = "You") -> Lead:
        lead = await self.get(user_id, lead_id)
        note = LeadNote(
            id=f"note_{_digest(lead_id + body + str(len(lead.notes)))}",
            body=body.strip(),
            author=author,
            created_at=datetime.now(UTC),
        )
        updated = lead.model_copy(
            update={"notes": [*lead.notes, note], "updated_at": datetime.now(UTC)}
        )
        await self.repo.save_lead(updated)
        return updated

    async def facets(self, user_id: str) -> tuple[list[str], list[Platform]]:
        """Filter options built from the data present, not a hardcoded list."""
        leads = await self.repo.list_leads(user_id)
        countries = sorted(
            {lead.location.country for lead in leads if lead.location and lead.location.country}
        )
        platforms: list[Platform] = []
        for lead in leads:
            for entry in lead.platforms:
                if entry.platform not in platforms:
                    platforms.append(entry.platform)
        return countries, platforms


def _filter(leads: list[Lead], query: LeadQuery) -> list[Lead]:
    needle = (query.query or "").strip().lower()
    out: list[Lead] = []

    for lead in leads:
        if not query.include_archived and lead.archived:
            continue
        if query.search_id and lead.search_id != query.search_id:
            continue
        if query.saved_only and not lead.saved:
            continue
        if query.min_score is not None and lead.score < query.min_score:
            continue
        if query.statuses and lead.status not in query.statuses:
            continue
        country = lead.location.country if lead.location else None
        if query.countries and country not in query.countries:
            continue
        if query.platforms and not any(
            entry.platform in query.platforms for entry in lead.platforms
        ):
            continue
        # Signal filters are AND: asking for MLM *and* leadership means both.
        if query.signals and not set(query.signals).issubset(lead.detected_signals()):
            continue
        if query.has_email and not lead.contacts.email:
            continue
        if query.has_social and not any(
            entry.platform in SOCIAL_PLATFORMS for entry in lead.platforms
        ):
            continue
        if needle and needle not in _haystack(lead):
            continue
        out.append(lead)

    return out


def _haystack(lead: Lead) -> str:
    location = lead.location
    parts = [
        lead.name,
        lead.headline,
        lead.company or "",
        location.city if location else "",
        location.country if location else "",
        lead.summary,
    ]
    return " ".join(part for part in parts if part).lower()


def _sort(leads: list[Lead], sort: LeadSort) -> list[Lead]:
    if sort is LeadSort.NAME_ASC:
        return sorted(leads, key=lambda lead: lead.name.lower())
    if sort is LeadSort.NEWEST:
        return sorted(leads, key=lambda lead: lead.created_at, reverse=True)
    return sorted(leads, key=lambda lead: (-lead.score, lead.name.lower()))


def _digest(value: str) -> str:
    return hashlib.sha1(value.encode()).hexdigest()[:10]
