"""Health payload (spec §21). `status: "ok"` is the contract; the rest is context."""

from app.schemas.common import CamelModel


class ProviderStatus(CamelModel):
    """Whether a provider key is configured — never the key itself (spec §55)."""

    brave_search: bool
    scrapegraph: bool
    openai: bool


class StageStatus(CamelModel):
    """
    Which adapter is behind each pipeline stage, so "is this real?" is answerable
    from outside: `search: "brave"` is the live web, `"fixture"` is the catalogue.
    """

    search: str
    extraction: str
    signals: str


class HealthOut(CamelModel):
    #: "degraded" when the API is up but the database is not answering.
    status: str = "ok"
    service: str
    version: str
    phase: int
    #: "fixture" (nothing external), "partial" (some stages live) or "live".
    pipeline: str
    stages: StageStatus
    #: Where the workspace lives — "postgres" since Phase 3.
    storage: str
    #: Whether the store just answered a query, not whether one is configured.
    database: bool = True
    providers: ProviderStatus
