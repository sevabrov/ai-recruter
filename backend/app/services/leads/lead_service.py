"""
Lead service (spec §14, §17, §57).

Ownership, note creation and the update rules live here; matching rows does not.
Phase 2 loaded every lead and filtered in Python because a dict cannot do better —
now the question travels to the database as one statement (`db/postgres.py`), and
this class stays what it should be: the place where a lead's lifecycle is decided.

The signatures did not change when the store did. `LeadQuery` moved to `app/models/`
so both sides of the seam can speak it.
"""

# `list` is a method name here, so annotations must stay lazy to keep the builtin.
from __future__ import annotations

import hashlib
from collections.abc import Sequence
from datetime import UTC, datetime

from app.core.errors import NotFoundError
from app.db.repository import Repository
from app.models.common import LeadStatus, Platform
from app.models.lead import Lead, LeadNote
from app.models.query import LeadQuery, LeadStats, Page


class LeadService:
    def __init__(self, repository: Repository) -> None:
        self.repo = repository

    async def list(self, user_id: str, query: LeadQuery) -> Page:
        return await self.repo.query_leads(user_id, query)

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
        # Appended as its own row, so two notes written at once cannot overwrite
        # each other the way a whole-document rewrite could.
        await self.repo.add_note(lead_id, note)
        return await self.get(user_id, lead_id)

    async def facets(self, user_id: str) -> tuple[list[str], list[Platform]]:
        """Filter options built from the data present, not a hardcoded list."""
        return await self.repo.lead_facets(user_id)

    async def stats(self, user_id: str, *, exclude_search_ids: Sequence[str] = ()) -> LeadStats:
        return await self.repo.lead_stats(user_id, exclude_search_ids=exclude_search_ids)


def _digest(value: str) -> str:
    return hashlib.sha1(value.encode()).hexdigest()[:10]
