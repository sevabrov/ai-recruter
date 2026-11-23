"""
AI Recruiter API — application entry point.

    uvicorn app.main:app --reload        (or: docker compose up -d backend)

Phase 5 scope: the endpoints from spec §57 behind the contract the frontend already
speaks, the search pipeline running end to end over PostgreSQL, live web search
(Phase 4) and — with a ScrapeGraphAI key — the candidate pages actually read and
extracted into the strict schema from §34, through a cache so no page is paid for
twice. Signal detection is still the keyword stand-in until Phase 6; see
`services/adapters.py` for what is plugged in where, and README.md for what each
later phase replaces.
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import dashboard, health, jobs, leads, searches, sources
from app.api.deps import close_container, open_container
from app.core.config import Settings, get_settings
from app.core.errors import register_error_handlers
from app.core.logging import configure_logging, get_logger
from app.models.lead import Lead

log = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings: Settings = app.state.settings
    configure_logging("DEBUG" if settings.debug else "INFO")

    container = await open_container(settings, app.state.catalogue)
    app.state.container = container
    log.info("api_started", extra={"phase": settings.phase, "storage": "postgres"})

    if settings.resume_running_searches:
        await _resume_interrupted(container)

    yield

    await close_container(container)
    log.info("api_stopped")


async def _resume_interrupted(container) -> None:
    """
    Now that searches are persisted this matters for real: a search interrupted by
    a restart is stored mid-flight, and re-queueing it is what a worker pool does on
    boot — nothing should sit frozen at 58%.
    """
    for search in await container.repository.list_searches(container.settings.dev_user_id):
        if search.is_running:
            await container.jobs.enqueue_search(search)
            log.info("search_resumed", extra={"search_id": search.id})


def create_app(settings: Settings | None = None, catalogue: list[Lead] | None = None) -> FastAPI:
    """
    `settings` is injectable so tests get a fast, quiet pipeline, and `catalogue`
    so the offline stand-ins have someone to find in tests. The app passes neither.
    """
    settings = settings or get_settings()
    app = FastAPI(
        title="AI Recruiter API",
        version=settings.version,
        summary="Lead discovery across the public web",
        lifespan=lifespan,
    )
    app.state.settings = settings
    app.state.catalogue = catalogue

    # The browser sends credentials, so origins must be listed explicitly.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    register_error_handlers(app)

    app.include_router(health.router)
    app.include_router(searches.router)
    app.include_router(leads.router)
    app.include_router(dashboard.router)
    app.include_router(jobs.router)
    app.include_router(sources.router)

    return app


app = create_app()
