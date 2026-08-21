"""
The scrape cache and what it records (spec §53, Milestone 5).

Two requirements meet in one table:

* **do not scrape the same URL twice** — a page read costs credits, and the same
  Instagram profile is found by four queries today and by tomorrow's search again.
  The cache is keyed by canonical URL, so `…/anna/` and `…/anna/?utm_source=x` are
  one entry (spec §31 does the normalising).
* **record which sources can actually be read** — the spec is explicit that not
  every social URL yields content. Every attempt is stored with its outcome, so
  "LinkedIn works, Instagram is blocked half the time" is a query rather than a
  hunch.

The cache is deliberately *not* scoped to a user: a page is a page. Ownership
lives on searches and leads, and nothing in here is derived from anyone's
criteria — only from the URL.
"""

from datetime import UTC, datetime, timedelta
from enum import StrEnum

from pydantic import BaseModel, Field

from app.models.common import Platform
from app.models.profile import ExtractedProfile


class ScrapeOutcome(StrEnum):
    """What happened when a reader was pointed at a page."""

    #: A person's profile came back.
    OK = "ok"
    #: The page was read and describes no person — a shop, a company, an article.
    NOT_A_PERSON = "not_a_person"
    #: The reader answered, with nothing in it.
    EMPTY = "empty"
    #: The page refused to be read: a login wall, a consent screen, a 403.
    BLOCKED = "blocked"
    #: The reader itself failed — a timeout, a rate limit, an outage.
    FAILED = "failed"


#: Outcomes that are an answer *about the page* and can therefore be reused. A
#: failure is about the reader, so it is recorded but never served from cache:
#: a service that was down for a minute must not make a URL unreadable for a week.
SETTLED_OUTCOMES: tuple[ScrapeOutcome, ...] = (
    ScrapeOutcome.OK,
    ScrapeOutcome.NOT_A_PERSON,
    ScrapeOutcome.EMPTY,
    ScrapeOutcome.BLOCKED,
)

#: Outcomes that mean the source gave us something worth having.
USABLE_OUTCOMES: tuple[ScrapeOutcome, ...] = (ScrapeOutcome.OK,)


class ScrapeRecord(BaseModel):
    """One row of the cache: a URL, when it was last read, and what came out."""

    canonical_url: str
    url: str
    platform: Platform
    #: Which reader produced this. A cached answer is only reused by the reader
    #: that wrote it — a better extractor must not inherit a worse one's verdicts.
    reader: str
    outcome: ScrapeOutcome
    #: Fingerprint of the extracted content (spec §53). ScrapeGraphAI returns
    #: structured JSON rather than the page body, so this hashes the JSON: the same
    #: hash means the page still says the same thing about the person.
    content_hash: str | None = None
    #: A short, safe note about a failure or a block — never the provider's key.
    detail: str | None = None
    attempts: int = 1
    profile: ExtractedProfile | None = None
    first_seen_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    last_scraped_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @property
    def settled(self) -> bool:
        return self.outcome in SETTLED_OUTCOMES

    def is_fresh(self, ttl_hours: int) -> bool:
        """
        Whether this answer may still be reused. A TTL of 0 disables the cache
        without deleting what it has learned about the sources.
        """
        if ttl_hours <= 0:
            return False
        age = datetime.now(UTC) - _aware(self.last_scraped_at)
        return age <= timedelta(hours=ttl_hours)

    def reusable(self, ttl_hours: int, reader: str) -> bool:
        return self.settled and self.reader == reader and self.is_fresh(ttl_hours)


class SourceReliability(BaseModel):
    """
    Per-platform reading record (Milestone 5: "record which sources consistently
    provide usable content"). Counted from the cache, so it is a measurement of
    this workspace's own attempts rather than a claim about the platforms.
    """

    platform: Platform
    pages: int = 0
    usable: int = 0
    not_a_person: int = 0
    empty: int = 0
    blocked: int = 0
    failed: int = 0
    last_read_at: datetime | None = None

    @property
    def usable_share(self) -> float:
        """0–1. Zero pages read is 0, not "perfect"."""
        return round(self.usable / self.pages, 3) if self.pages else 0.0


def _aware(moment: datetime) -> datetime:
    return moment if moment.tzinfo else moment.replace(tzinfo=UTC)
