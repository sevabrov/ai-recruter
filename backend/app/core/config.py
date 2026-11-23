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
    version: str = "0.5.2"
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
    #: Reads the client's free-text brief into criteria (one call per brief).
    #: gpt-4.1 because it was the one of four compared on the same Ukrainian brief
    #: that kept brand spellings in both scripts and one must-have, at under 2 s.
    openai_model: str = "gpt-4.1"
    openai_endpoint: str = "https://api.openai.com/v1/chat/completions"
    openai_timeout_seconds: float = 30.0
    #: Judge candidates against the search's requirements with the model (Phase 6),
    #: whenever a key is set. `false` keeps the free keyword judge.
    llm_signals: bool = True
    #: One call per candidate, so the cheap model: the question is narrow ("is this
    #: in the text, and where?") and every quote it returns is checked by code.
    openai_judge_model: str = "gpt-4.1-mini"
    #: Model judgements bought per lead asked for: a search for 10 leads may have 100
    #: candidates judged. Measured: a strict network-marketing search accepted 4 of
    #: the first 60 it judged, so a fixed 60 ran out long before 10 leads.
    judgements_per_lead: int = 10
    #: …and how many a lead *usually* takes, for the expected price next to the
    #: ceiling. Measured over fourteen runs (November 2026): 1.5 to 3.8 judged
    #: candidates per lead asked for — the search stops once it has enough.
    expected_judgements_per_lead: int = 4
    #: The most candidates one search may have judged by the model, whatever it asks
    #: for. Past the budget candidates are judged by their words, for free — which is
    #: what lets the wizard quote a ceiling: candidates whose pages are never read are
    #: judged too, and there can be many more of them than pages.
    max_judgements_per_search: int = 300
    #: Candidates judged in one model call. The instructions and the requirements
    #: go once per batch, which is most of a call's tokens.
    judge_batch_size: int = 6
    google_cse_api_key: str = ""
    google_cse_engine_id: str = ""
    #: "brave" — live as soon as the key is there; "fixture" — never, whatever keys
    #: are set, which is what the test suite wants.
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
    #: a run against the dashboard and set it to what actually moved. The documented
    #: price of an Extract call is five.
    scrapegraph_credits_per_page: int = 5
    #: …and what the residential proxy adds on top, per the same documentation.
    scrapegraph_stealth_credits: int = 5
    #: Fetch social profiles through the provider's residential proxy, with the page
    #: rendered before it is read (`fetchConfig.stealth`).
    #:
    #: On by default because the measurement was decisive: without it, 20 of 23
    #: Instagram pages and 15 of 15 Facebook pages came back 502/504 — a datacentre
    #: address asking for un-rendered HTML is the request a social network is surest
    #: to refuse. It doubles the price of those pages, and only the platforms that
    #: need it pay (`scrapegraph_extractor.STEALTH_PLATFORMS`): a personal website
    #: is read the cheap way.
    scrapegraph_stealth: bool = True
    #: How long to let a page settle after it loads, in milliseconds. A profile is a
    #: JavaScript application; its bio is not in the first response.
    scrapegraph_page_wait_ms: int = 2000

    # ------------------------------------- our own browser (Instagram, Facebook)
    #: Read public Instagram profiles and Facebook pages with a headless Chromium on
    #: this server instead of ScrapeGraphAI. Measured: the provider opened 8 of 145
    #: Instagram profiles, the browser — without logging in, from a datacentre —
    #: 20 of 20. Free per page. LinkedIn stays with ScrapeGraphAI (a browser without
    #: a login gets a sign-up wall there). Only with live search.
    browser_reader: bool = True
    #: Pages open at once. One browser, shared by every search on this server.
    browser_concurrency: int = 4
    #: How long one page may take before its search result is used instead.
    browser_timeout_seconds: float = 15.0

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
    #: The wizard sets this per search; this value is the default it starts from.
    target_leads: int = 0
    #: How many pages one lead costs, used to turn "find me 10 leads" into a page
    #: budget and a price the wizard can show before anything is spent. Not a
    #: guess to be left alone: the run reports both numbers, so set this to what a
    #: finished search actually measured (pagesRead ÷ leads).
    pages_per_lead: int = 3
    #: The ceiling on generated queries, and therefore on billed search calls. One
    #: query is one call (€0.005 on Brave's Base plan), and a search asked for in
    #: three languages writes three sets of them — so the money side of asking in
    #: more languages needs a limit of its own. The wizard shows the real number
    #: before the search starts; this is only the maximum it may reach.
    max_queries_per_search: int = 24

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
    #: One candidate judged by gpt-4.1-mini, in a batch of six: ~0.7k tokens in and
    #: ~0.2k out each, the shared instructions included. A ceiling.
    cost_per_llm_call_eur: float = 0.0008

    # --------------------------------------------------------------- pipeline
    # Pacing, not throttling. The offline stand-ins answer instantly, so a
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
