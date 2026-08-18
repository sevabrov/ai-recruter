"""
Configuration (spec §22, §52).

Every limit is configuration, never a hardcoded constant, and provider keys are
read here only — no other module touches os.environ. Values come from the
process environment, which docker compose fills from the repository-root `.env`.
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        # Local runs read the same file compose passes in as env_file.
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ------------------------------------------------------------------ app
    app_name: str = "ai-recruiter-api"
    version: str = "0.3.0"
    phase: int = 3
    debug: bool = True

    # Browsers must be able to talk to us with credentials, so origins are
    # explicit — a wildcard is invalid together with allow_credentials.
    cors_origins: list[str] = ["http://localhost:3000", "http://127.0.0.1:3000"]

    # Until Phase 8 introduces real accounts every request is attributed to this
    # single owner. The ownership check in api/deps.py already runs against it.
    dev_user_id: str = "user_demo"

    # ------------------------------------------------------------ persistence
    # The default is the host-side URL, so `uvicorn app.main:app` on a laptop finds
    # the compose Postgres. Inside compose the service name is passed in instead.
    database_url: str = "postgresql+asyncpg://airecruiter:airecruiter@localhost:5432/airecruiter"
    # The pool has to cover the pipeline's per-stage workers (see the concurrency
    # limits below) plus the requests arriving while a search runs.
    db_pool_size: int = 10
    db_max_overflow: int = 10
    #: Log every statement. Useful when a query looks wrong, far too loud otherwise.
    db_echo: bool = False
    #: `alembic upgrade head` during startup, so one command brings up a new volume.
    run_migrations_on_startup: bool = True

    # Phase 7 (Celery broker). Not connected yet.
    redis_url: str = "redis://localhost:6379/0"

    # -------------------------------------------------------------- providers
    # Phase 4–6. Empty means "not configured": the pipeline falls back to the
    # fixture adapters and says so in the response.
    brave_search_api_key: str = ""
    scrapegraph_api_key: str = ""
    openai_api_key: str = ""
    google_cse_api_key: str = ""
    google_cse_engine_id: str = ""
    search_provider: str = "brave"

    # ----------------------------------------------------- limits (spec §52)
    search_concurrency: int = 10
    extraction_concurrency: int = 10
    llm_concurrency: int = 10
    max_retries: int = 3
    scrape_cache_ttl_hours: int = 168

    # ------------------------------------------------ cost model (spec §54)
    cost_per_search_call_eur: float = 0.005
    cost_per_page_eur: float = 0.010
    cost_per_llm_call_eur: float = 0.004

    # --------------------------------------------------------------- pipeline
    # Demo pacing, not throttling. The fixture adapters answer instantly, so a
    # whole search would finish in about a second and the progress screen would
    # never be seen. Each pipeline step therefore pauses briefly, which keeps the
    # run in the "seconds, not minutes" band the spec asks for (§13).
    # Set to 0 for an instant demo; real providers bring their own latency and
    # this drops to 0 for good in Phase 4.
    pipeline_step_delay_ms: int = 250

    # A search left mid-flight by a restart is re-queued at startup instead of
    # sitting frozen. Tests turn this off to keep their fixtures still.
    resume_running_searches: bool = True


@lru_cache
def get_settings() -> Settings:
    return Settings()
