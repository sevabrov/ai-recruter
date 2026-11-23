"""
The test workspace.

`data/workspace.json` holds four searches and the 24 leads they found. The app
ships none of it: every test starts from an empty database, and `conftest.py`
inserts this file, then hands its leads to the app as the catalogue the offline
stand-ins (no Brave key) search over. A new search therefore rediscovers these
people through the real pipeline and re-scores them against its criteria.

Timestamps are rebased on load: the newest moment in the file becomes "now", which
keeps "3 hours ago" honest however long the file sits in git.
"""

import json
from datetime import datetime, timedelta
from functools import lru_cache
from pathlib import Path
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from app.db.mappers import apply_lead, apply_search, note_row
from app.db.tables import LeadRow, SearchRow, UserRow
from app.models.lead import Lead
from app.models.search import Search
from app.schemas.lead import LeadOut
from app.schemas.search import SearchOut

WORKSPACE_FILE = Path(__file__).parent / "data" / "workspace.json"

TIME_KEYS = {"createdAt", "startedAt", "completedAt", "updatedAt", "discoveredAt"}


class Workspace:
    """The parsed workspace file."""

    def __init__(self, raw: dict[str, Any], user_id: str) -> None:
        self.user_id = user_id
        shifted = _rebase(raw)
        self.searches: list[Search] = [_to_search(entry, user_id) for entry in shifted["searches"]]
        self.leads: list[Lead] = [_to_lead(entry, user_id) for entry in shifted["leads"]]

    @property
    def catalogue(self) -> list[Lead]:
        """
        The candidate pool the offline stand-ins draw from. These are the same
        people the stored searches found; a new search rediscovers them through
        the real pipeline and re-scores them against the new criteria.
        """
        return self.leads


@lru_cache
def load_workspace(user_id: str) -> Workspace:
    raw = json.loads(WORKSPACE_FILE.read_text(encoding="utf-8"))
    return Workspace(raw, user_id)


async def insert_workspace(url: str, workspace: Workspace) -> None:
    """Write the workspace into an empty database: owner, searches, leads, notes."""
    engine = create_async_engine(url, poolclass=NullPool)
    try:
        async with AsyncSession(engine) as session, session.begin():
            session.add(UserRow(id=workspace.user_id))
            await session.flush()
            for search in workspace.searches:
                session.add(apply_search(SearchRow(), search))
            await session.flush()
            for lead in workspace.leads:
                session.add(apply_lead(LeadRow(), lead))
                for note in lead.notes:
                    session.add(note_row(lead.id, note))
    finally:
        await engine.dispose()


def _to_search(entry: dict[str, Any], user_id: str) -> Search:
    # The API schema already speaks camelCase, so it doubles as the workspace parser;
    # dumping by field name hands the domain model snake_case keys.
    parsed = SearchOut.model_validate(entry).model_dump()
    return Search(user_id=user_id, **parsed)


def _to_lead(entry: dict[str, Any], user_id: str) -> Lead:
    parsed = LeadOut.model_validate(entry).model_dump()
    return Lead(user_id=user_id, **parsed)


def _rebase(raw: dict[str, Any]) -> dict[str, Any]:
    """Shift every timestamp so the most recent fixture event is right now."""
    latest = _latest(raw)
    if latest is None:
        return raw
    offset = datetime.now(latest.tzinfo) - latest
    return _walk(raw, offset)


def _latest(node: Any) -> datetime | None:
    found: datetime | None = None
    for value in _timestamps(node):
        if found is None or value > found:
            found = value
    return found


def _timestamps(node: Any) -> list[datetime]:
    out: list[datetime] = []
    if isinstance(node, dict):
        for key, value in node.items():
            if key in TIME_KEYS and isinstance(value, str):
                parsed = _parse(value)
                if parsed:
                    out.append(parsed)
            else:
                out.extend(_timestamps(value))
    elif isinstance(node, list):
        for item in node:
            out.extend(_timestamps(item))
    return out


def _walk(node: Any, offset: timedelta) -> Any:
    if isinstance(node, dict):
        result = {}
        for key, value in node.items():
            if key in TIME_KEYS and isinstance(value, str):
                parsed = _parse(value)
                result[key] = (parsed + offset).isoformat() if parsed else value
            else:
                result[key] = _walk(value, offset)
        return result
    if isinstance(node, list):
        return [_walk(item, offset) for item in node]
    return node


def _parse(value: str) -> datetime | None:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
