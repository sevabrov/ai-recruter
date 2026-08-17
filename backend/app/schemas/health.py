"""Health payload (spec §21). `status: "ok"` is the contract; the rest is context."""

from app.schemas.common import CamelModel


class ProviderStatus(CamelModel):
    """Whether a provider key is configured — never the key itself (spec §55)."""

    brave_search: bool
    scrapegraph: bool
    openai: bool


class HealthOut(CamelModel):
    status: str = "ok"
    service: str
    version: str
    phase: int
    #: "fixture" until Phase 4–6 replace the stub adapters with real providers.
    pipeline: str
    #: "memory" until Phase 3 introduces PostgreSQL.
    storage: str
    providers: ProviderStatus
