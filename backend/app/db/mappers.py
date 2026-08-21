"""
Rows ↔ domain models.

The only file that knows both shapes. Everything above it works with the Pydantic
models from `app/models/`; everything below it works with the tables in
`app/db/tables.py`. Two details are worth naming:

* `GeoLocation` and `LeadContacts` are flattened into columns on the way in and
  rebuilt on the way out, so `location.country` can be indexed and faceted;
* `platform_kinds` and `detected_signals` are derived here, never set by a caller.
  They are query mirrors of the `platforms` and `signals` documents, so they are
  recomputed on every write and cannot drift from what is displayed.
"""

import hashlib
from typing import Any

from app.db.tables import JobRow, LeadNoteRow, LeadRow, ScrapeRow, SearchRow
from app.models.job import Job
from app.models.lead import Lead, LeadNote
from app.models.scrape import ScrapeRecord
from app.models.search import Search


# ------------------------------------------------------------------- searches
def apply_search(row: SearchRow, search: Search) -> SearchRow:
    row.id = search.id
    row.user_id = search.user_id
    row.name = search.name
    row.status = search.status.value
    row.created_at = search.created_at
    row.started_at = search.started_at
    row.completed_at = search.completed_at
    row.lead_count = search.lead_count
    row.high_quality_count = search.high_quality_count
    row.target = search.target
    row.country = search.country
    row.sources = [source.value for source in search.sources]
    row.criteria = search.criteria.model_dump(mode="json")
    row.progress = search.progress.model_dump(mode="json")
    row.usage = search.usage.model_dump(mode="json")
    row.queries = [entry.model_dump(mode="json") for entry in search.queries]
    row.error = search.error
    return row


def to_search(row: SearchRow) -> Search:
    return Search.model_validate(
        {
            "id": row.id,
            "user_id": row.user_id,
            "name": row.name,
            "status": row.status,
            "created_at": row.created_at,
            "started_at": row.started_at,
            "completed_at": row.completed_at,
            "lead_count": row.lead_count,
            "high_quality_count": row.high_quality_count,
            "target": row.target,
            "country": row.country,
            "sources": row.sources,
            "criteria": row.criteria,
            "progress": row.progress,
            "usage": row.usage,
            "queries": row.queries,
            "error": row.error,
        }
    )


# ---------------------------------------------------------------------- leads
def apply_lead(row: LeadRow, lead: Lead) -> LeadRow:
    location = lead.location
    row.id = lead.id
    row.user_id = lead.user_id
    row.search_id = lead.search_id
    row.search_name = lead.search_name
    row.name = lead.name
    row.headline = lead.headline
    row.company = lead.company
    row.summary = lead.summary
    row.country = location.country if location else None
    row.region = location.region if location else None
    row.city = location.city if location else None
    row.languages = list(lead.languages)
    row.score = lead.score
    row.score_breakdown = [entry.model_dump(mode="json") for entry in lead.score_breakdown]
    row.platforms = [entry.model_dump(mode="json") for entry in lead.platforms]
    row.signals = [signal.model_dump(mode="json") for signal in lead.signals]
    row.sources = [source.model_dump(mode="json") for source in lead.sources]
    row.platform_kinds = [entry.platform.value for entry in lead.platforms]
    row.detected_signals = sorted(signal.value for signal in lead.detected_signals())
    row.email = lead.contacts.email
    row.website = lead.contacts.website
    row.phone = lead.contacts.phone
    row.status = lead.status.value
    row.saved = lead.saved
    row.archived = lead.archived
    row.created_at = lead.created_at
    row.updated_at = lead.updated_at
    row.merged_urls = list(lead.merged_urls)
    return row


def to_lead(row: LeadRow) -> Lead:
    return Lead.model_validate(
        {
            "id": row.id,
            "user_id": row.user_id,
            "search_id": row.search_id,
            "search_name": row.search_name,
            "name": row.name,
            "headline": row.headline,
            "company": row.company,
            "location": _location(row),
            "languages": row.languages,
            "score": row.score,
            "score_breakdown": row.score_breakdown,
            "platforms": row.platforms,
            "summary": row.summary,
            "signals": row.signals,
            "sources": row.sources,
            "contacts": {"email": row.email, "website": row.website, "phone": row.phone},
            "status": row.status,
            "saved": row.saved,
            "archived": row.archived,
            "notes": [to_note(note) for note in row.notes],
            "created_at": row.created_at,
            "updated_at": row.updated_at,
            "merged_urls": row.merged_urls,
        }
    )


def _location(row: LeadRow) -> dict[str, Any] | None:
    if not (row.country or row.region or row.city):
        return None
    return {"country": row.country, "region": row.region, "city": row.city}


def note_row(lead_id: str, note: LeadNote) -> LeadNoteRow:
    return LeadNoteRow(
        id=note.id,
        lead_id=lead_id,
        body=note.body,
        author=note.author,
        created_at=note.created_at,
    )


def to_note(row: LeadNoteRow) -> dict[str, Any]:
    return {
        "id": row.id,
        "body": row.body,
        "author": row.author,
        "created_at": row.created_at,
    }


# ----------------------------------------------------------------------- jobs
def apply_job(row: JobRow, job: Job) -> JobRow:
    row.id = job.id
    row.kind = job.kind.value
    row.status = job.status.value
    row.search_id = job.search_id
    row.user_id = job.user_id
    row.attempts = job.attempts
    row.error = job.error
    row.created_at = job.created_at
    row.started_at = job.started_at
    row.finished_at = job.finished_at
    return row


def to_job(row: JobRow) -> Job:
    return Job.model_validate(
        {
            "id": row.id,
            "kind": row.kind,
            "status": row.status,
            "search_id": row.search_id,
            "user_id": row.user_id,
            "attempts": row.attempts,
            "error": row.error,
            "created_at": row.created_at,
            "started_at": row.started_at,
            "finished_at": row.finished_at,
        }
    )


# --------------------------------------------------------------- scrape cache
def scrape_key(canonical_url: str) -> str:
    """The row's identity: one canonical URL is one entry, however long it is."""
    return hashlib.sha256(canonical_url.encode()).hexdigest()[:64]


def apply_scrape(row: ScrapeRow, record: ScrapeRecord) -> ScrapeRow:
    row.key = scrape_key(record.canonical_url)
    row.canonical_url = record.canonical_url
    row.url = record.url
    row.platform = record.platform.value
    row.reader = record.reader
    row.outcome = record.outcome.value
    row.content_hash = record.content_hash
    row.detail = record.detail
    row.attempts = record.attempts
    row.profile = record.profile.model_dump(mode="json") if record.profile else None
    row.first_seen_at = record.first_seen_at
    row.last_scraped_at = record.last_scraped_at
    return row


def to_scrape(row: ScrapeRow) -> ScrapeRecord:
    return ScrapeRecord.model_validate(
        {
            "canonical_url": row.canonical_url,
            "url": row.url,
            "platform": row.platform,
            "reader": row.reader,
            "outcome": row.outcome,
            "content_hash": row.content_hash,
            "detail": row.detail,
            "attempts": row.attempts,
            "profile": row.profile,
            "first_seen_at": row.first_seen_at,
            "last_scraped_at": row.last_scraped_at,
        }
    )
