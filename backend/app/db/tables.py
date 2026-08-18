"""
The schema (spec §23).

Two rules decide whether something gets a column of its own:

* **anything the product filters, sorts or counts by is a column** — score,
  country, status, saved, archived, created_at. Those are the WHERE and ORDER BY
  clauses behind `/leads`, so they must be indexable, not buried in a document.
* **everything else is JSONB** — the evidence-bearing value objects (signals,
  score breakdown, platforms, sources, criteria, progress, usage) are read and
  written whole, never queried field by field. Storing them as documents keeps
  one definition of their shape (the Pydantic models in `app/models/`) instead of
  a second one spread over a dozen child tables.

The two filters that need both are `platforms` and `signals`: the full objects
live in JSONB for display, and a flat `text[]` mirror exists for querying, so
"has a LinkedIn profile" and "MLM *and* leadership were detected" are index-backed
array operations rather than document scans. `app/db/mappers.py` is the only place
that knows the mirror exists.

Notes are a real child table: they are appended one at a time by a user action,
which is exactly the case a document column handles badly.
"""

from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    text,
)

# The postgresql ARRAY, not the generic one: `&&` (overlap) and `@>` (contains)
# are what the platform and signal filters compile to.
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


def _now() -> Any:
    """Server-side default, so a clock skew on the API host cannot reorder rows."""
    return text("now()")


class UserRow(Base):
    """
    Phase 8 fills this table from real sign-ups. Until then it holds exactly one
    row — but the ownership column on every other table is a real foreign key
    from day one, so scoping queries by user is never bolted on later (spec §55).
    """

    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    email: Mapped[str | None] = mapped_column(String(320))
    name: Mapped[str | None] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=_now())


class SearchRow(Base):
    """One search run (spec §24): the request, how far it got and what it cost."""

    __tablename__ = "searches"
    __table_args__ = (Index("ix_searches_user_created", "user_id", "created_at"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    lead_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    high_quality_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    target: Mapped[str] = mapped_column(String(300), nullable=False, default="")
    country: Mapped[str | None] = mapped_column(String(120))

    # Documents: written and read whole by the pipeline and the progress screen.
    sources: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    criteria: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    progress: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    usage: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    queries: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list)
    error: Mapped[str | None] = mapped_column(Text)

    leads: Mapped[list["LeadRow"]] = relationship(
        back_populates="search", cascade="all, delete-orphan", passive_deletes=True
    )


class LeadRow(Base):
    """A discovered person (spec §25) with the evidence behind their score."""

    __tablename__ = "leads"
    __table_args__ = (
        # The results screen sorts by score inside one search.
        Index("ix_leads_user_score", "user_id", "score"),
        Index("ix_leads_search_score", "search_id", "score"),
        # Array containment/overlap is only cheap with GIN behind it.
        Index("ix_leads_platform_kinds", "platform_kinds", postgresql_using="gin"),
        Index("ix_leads_detected_signals", "detected_signals", postgresql_using="gin"),
    )

    id: Mapped[str] = mapped_column(String(160), primary_key=True)
    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    search_id: Mapped[str] = mapped_column(
        ForeignKey("searches.id", ondelete="CASCADE"), nullable=False, index=True
    )
    search_name: Mapped[str] = mapped_column(String(200), nullable=False, default="")

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    headline: Mapped[str] = mapped_column(Text, nullable=False, default="")
    company: Mapped[str | None] = mapped_column(String(200))
    summary: Mapped[str] = mapped_column(Text, nullable=False, default="")

    # GeoLocation is flattened: country is a filter and a facet, so it is a column.
    country: Mapped[str | None] = mapped_column(String(120), index=True)
    region: Mapped[str | None] = mapped_column(String(120))
    city: Mapped[str | None] = mapped_column(String(120))
    languages: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)

    score: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    score_breakdown: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, default=list
    )

    platforms: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list)
    signals: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list)
    sources: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list)

    #: Queryable mirrors of the two documents above — see the module docstring.
    platform_kinds: Mapped[list[str]] = mapped_column(
        ARRAY(String), nullable=False, default=list, server_default="{}"
    )
    detected_signals: Mapped[list[str]] = mapped_column(
        ARRAY(String), nullable=False, default=list, server_default="{}"
    )

    email: Mapped[str | None] = mapped_column(String(320))
    website: Mapped[str | None] = mapped_column(String(500))
    phone: Mapped[str | None] = mapped_column(String(64))

    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    saved: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    archived: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    #: Canonical URLs this person was merged from (spec §45).
    merged_urls: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)

    search: Mapped[SearchRow] = relationship(back_populates="leads")
    notes: Mapped[list["LeadNoteRow"]] = relationship(
        back_populates="lead",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="LeadNoteRow.created_at, LeadNoteRow.id",
        # Loaded with the lead: a lead is never shown without its notes, and the
        # async session must not lazy-load on attribute access.
        lazy="selectin",
    )


class LeadNoteRow(Base):
    """Appended by a user, one at a time — hence a table rather than a document."""

    __tablename__ = "lead_notes"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    lead_id: Mapped[str] = mapped_column(
        ForeignKey("leads.id", ondelete="CASCADE"), nullable=False, index=True
    )
    body: Mapped[str] = mapped_column(Text, nullable=False)
    author: Mapped[str] = mapped_column(String(120), nullable=False, default="You")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    lead: Mapped[LeadRow] = relationship(back_populates="notes")


class JobRow(Base):
    """
    Background work (spec §39–40). Phase 2 kept jobs in memory, so a restart lost
    the audit trail; now `GET /jobs` survives one. Phase 7 hands these same rows
    to Celery.
    """

    __tablename__ = "jobs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    search_id: Mapped[str | None] = mapped_column(
        ForeignKey("searches.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class SeedStateRow(Base):
    """
    Why the seed is applied once and not on every boot.

    Without a marker, an empty workspace and a *deliberately emptied* workspace
    look identical, so the demo data would grow back after every restart. This row
    records that it was applied; `POST /admin/reset` deletes it and re-applies.
    """

    __tablename__ = "seed_state"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    applied_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=_now())
    searches: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    leads: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
