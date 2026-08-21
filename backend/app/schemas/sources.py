"""
Source reliability (Milestone 5: *"record which sources consistently provide
usable content"*).

Counted from the scrape cache, so this is a measurement of what this workspace's
own reads returned — not a claim about the platforms in general, and not a guess.
"""

from datetime import datetime

from app.models.common import Platform
from app.schemas.common import CamelModel


class SourceReliabilityOut(CamelModel):
    platform: Platform
    #: Distinct pages this platform was read for.
    pages: int
    #: …of which yielded a person's profile.
    usable: int
    #: The page was read and describes no person: a shop, a company, an article.
    not_a_person: int
    #: The reader answered with nothing in it.
    empty: int
    #: A login wall, a consent screen, a refusal.
    blocked: int
    #: The reader itself failed — a timeout, a rate limit, a rejected key.
    failed: int
    #: `usable / pages`, 0–1. Zero pages read is 0, not "perfect".
    usable_share: float
    last_read_at: datetime | None = None


class SourcesOut(CamelModel):
    #: Which adapter reads pages ("scrapegraph"), or the stand-in that stands in.
    reader: str
    #: Whether pages are actually being fetched, as opposed to read off the results.
    live: bool
    #: How long a page's extraction is reused before it is read again (spec §53).
    cache_ttl_hours: int
    #: What happens to a page that will not open, in words the UI can show.
    fallback: str
    #: What one search may spend and aim for. Null means "no limit" in both cases —
    #: the UI needs the difference between "unlimited" and "zero".
    max_pages_per_search: int | None = None
    target_leads: int | None = None
    #: What one page is assumed to cost in plan units, since the API does not say.
    credits_per_page: int = 0
    items: list[SourceReliabilityOut]
