"""
Seed data.

`seed/fixtures.json` is generated from the Phase 1 frontend fixtures
(`frontend/src/mocks/*.ts`) so the approved demo content is served by the API
byte-for-byte instead of being re-typed here. Regenerate with:

    node --experimental-strip-types --import ./register.mjs dump.mjs fixtures.json

Timestamps are rebased on load: the newest fixture moment becomes "now", which
keeps "3 hours ago" honest however long the file sits in git. Phase 3 loads the
same file into PostgreSQL once, instead of on every boot.
"""

import json
from datetime import datetime, timedelta
from functools import lru_cache
from pathlib import Path
from typing import Any

from app.models.lead import Lead
from app.models.search import Search
from app.schemas.dashboard import ScoreBucket, SourceShare, WeeklyPoint
from app.schemas.lead import LeadOut
from app.schemas.search import SearchOut

SEED_FILE = Path(__file__).parent / "seed" / "fixtures.json"

TIME_KEYS = {"createdAt", "startedAt", "completedAt", "updatedAt", "discoveredAt"}


class SeedData:
    """The parsed seed: entities plus the aggregates the dashboard starts from."""

    def __init__(self, raw: dict[str, Any], user_id: str) -> None:
        shifted = _rebase(raw)
        self.searches: list[Search] = [_to_search(entry, user_id) for entry in shifted["searches"]]
        self.leads: list[Lead] = [_to_lead(entry, user_id) for entry in shifted["leads"]]

        dashboard = shifted["dashboard"]
        self.stats: dict[str, Any] = dashboard["stats"]
        self.source_breakdown = [
            SourceShare.model_validate(row) for row in dashboard["sourceBreakdown"]
        ]
        self.score_distribution = [
            ScoreBucket.model_validate(row) for row in dashboard["scoreDistribution"]
        ]
        self.weekly_leads = [WeeklyPoint.model_validate(row) for row in dashboard["weeklyLeads"]]

    @property
    def catalogue(self) -> list[Lead]:
        """
        The candidate pool the fixture adapters draw from. These are the same
        people the seeded searches found; a new search rediscovers them through
        the real pipeline and re-scores them against the new criteria.
        """
        return self.leads


@lru_cache
def load_seed(user_id: str) -> SeedData:
    raw = json.loads(SEED_FILE.read_text(encoding="utf-8"))
    return SeedData(raw, user_id)


def _to_search(entry: dict[str, Any], user_id: str) -> Search:
    # The API schema already speaks camelCase, so it doubles as the seed parser;
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
