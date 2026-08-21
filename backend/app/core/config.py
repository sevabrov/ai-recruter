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
    version: str = "0.5.1"
    phase: int = 5
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
    # Empty means "not configured": the pipeline falls back to a stand-in adapter
    # and `/health` reports which stage is live (spec §46–47).
    brave_search_api_key: str = ""
    scrapegraph_api_key: str = ""
    openai_api_key: str = ""
    google_cse_api_key: str = ""
    google_cse_engine_id: str = ""
    #: "brave" — live as soon as the key is there; "fixture" — never, whatever keys
    #: are set, which is what the test suite and an offline demo want.
    search_provider: str = "brave"

    # ---------------------------------------------- Brave Search (spec §28, §52)
    brave_endpoint: str = "https://api.search.brave.com/res/v1/web/search"
    #: Brave's own maximum per request is 20, and one query stays one billed call.
    brave_results_per_query: int = 20
    brave_timeout_seconds: float = 10.0
    #: The free and Base plans allow one request per second *per key*, so this is a
    #: property of the subscription rather than of a search. Raise it with the plan;
    #: 0 turns the throttle off.
    brave_rate_limit_per_second: float = 1.0
    #: A professional lead search should see public profiles the default filter can
    #: hide; "moderate" and "strict" are the other values Brave accepts.
    brave_safesearch: str = "off"

    # -------------------------------------------- ScrapeGraphAI (spec §33, §53)
    #: The v2 Extract service. Configuration rather than a constant because the
    #: legacy `api.scrapegraphai.com/v1/smartscraper` host is deprecated but still
    #: answers for older accounts — either one works without a code change.
    scrapegraph_endpoint: str = "https://v2-api.scrapegraphai.com/api/extract"
    #: Reading a page is not a search: it fetches, renders and extracts, so seconds.
    scrapegraph_timeout_seconds: float = 120.0
    #: Per key, like every provider limit here. Lower it to match a smaller plan.
    scrapegraph_rate_limit_per_second: float = 1.0
    #: When a page cannot be read, build the profile from the search result instead
    #: of losing the lead. False makes unreadable pages simply disappear.
    scrapegraph_fallback_to_snippets: bool = True
    #: How many times *one page* may be read. One, deliberately: the service bills a
    #: request it served, and our timeout does not un-bill it — a retry pays for the
    #: same page again. The page falls back to its search snippet instead.
    scrapegraph_read_attempts: int = 1
    #: What one page costs in the plan's own units. The v2 response does not report
    #: credits, so this is the only way the credit counter can be truthful — measure
    #: a run against the dashboard and set it to what actually moved.
    scrapegraph_credits_per_page: int = 10

    # ----------------------------------------------------- limits (spec §52)
    search_concurrency: int = 10
    extraction_concurrency: int = 10
    llm_concurrency: int = 10
    max_retries: int = 3
    #: How long a page's extraction may be reused (spec §53). A week: profiles change
    #: slowly, and re-reading one is a paid request. 0 disables the cache.
    scrape_cache_ttl_hours: int = 168

    # --------------------------------------------------- what one search may spend
    #: The ceiling on *paid* page reads in a single search. A live search finds
    #: 100+ candidate pages, and reading all of them is the difference between
    #: cents and a plan's monthly credits. Candidates past the budget still become
    #: leads — from their search snippet, for free — so the limit costs depth, not
    #: coverage. Cache hits are not paid reads and never count against it.
    #: 0 means unlimited, which is what the fixture demo and the tests want.
    max_pages_per_search: int = 25
    #: "Find me this many leads." Reached, the search stops reading and stops
    #: judging: candidates are processed best-first, so stopping early drops the
    #: weakest ones rather than an arbitrary tail. 0 means "as many as there are".
    target_leads: int = 0

    # ------------------------------------------------ cost model (spec §54)
    cost_per_search_call_eur: float = 0.005
    #: What one *paid request* to the page reader costs. Billed per request the
    #: service served — including one that answered too late for us to use, because
    #: the credit went either way. Cached pages and pages the budget refused are
    #: free and are counted separately, so the figure stays a measurement.
    cost_per_page_eur: float = 0.010
    #: Charged per judged profile, and only while a detector that really calls an
    #: LLM is plugged in: the keyword stand-in costs nothing, and billing it would
    #: put money on the usage screen that nobody spent.
    cost_per_llm_call_eur: float = 0.004

    # --------------------------------------------------------------- pipeline
    # Demo pacing, not throttling. The fixture adapters answer instantly, so a
    # whole search would finish in about a second and the progress screen would
    # never be seen. Each pipeline step therefore pauses briefly, which keeps the
    # run in the "seconds, not minutes" band the spec asks for (§13).
    # Ignored once live search is on: a real provider brings its own latency
    # (see api/deps.py). Set to 0 for an instant fixture run.
    pipeline_step_delay_ms: int = 250

    # A search left mid-flight by a restart is re-queued at startup instead of
    # sitting frozen. Tests turn this off to keep their fixtures still.
    resume_running_searches: bool = True


@lru_cache
def get_settings() -> Settings:
    return Settings()
