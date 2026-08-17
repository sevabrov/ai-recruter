"""
AI Recruiter API — application entry point.

    uvicorn app.main:app --reload        (or: docker compose up -d backend)

Phase 2 scope: the endpoints from spec §57 behind the contract the frontend
already speaks, with the search pipeline running end to end on fixture adapters.
No external service is called and no database is required — see `services/adapters.py`
for exactly where the real providers plug in, and README.md for what each later
phase replaces.
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import admin, dashboard, health, jobs, leads, searches
from app.api.deps import build_container
from app.core.config import Settings, get_settings
from app.core.errors import register_error_handlers
from app.core.logging import configure_logging, get_logger

log = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings: Settings = app.state.settings
    configure_logging("DEBUG" if settings.debug else "INFO")

    container = build_container(settings)
    app.state.container = container
    log.info(
        "api_started",
        extra={
            "phase": settings.phase,
            "searches": len(container.seed.searches),
            "leads": len(container.seed.leads),
        },
    )

    if settings.resume_running_searches:
        await _resume_interrupted(container)

    yield

    await container.jobs.shutdown()
    log.info("api_stopped")


async def _resume_interrupted(container) -> None:
    """
    The seed contains a search that was still running when it was captured, and a
    real restart can leave one behind too. Re-queueing them is what a worker pool
    does on boot — nothing should sit frozen at 58%.
    """
    for search in await container.repository.list_searches(container.settings.dev_user_id):
        if search.is_running:
            await container.jobs.enqueue_search(search)
            log.info("search_resumed", extra={"search_id": search.id})


def create_app(settings: Settings | None = None) -> FastAPI:
    """`settings` is injectable so tests get a fast, quiet pipeline."""
    settings = settings or get_settings()
    app = FastAPI(
        title="AI Recruiter API",
        version=settings.version,
        summary="Lead discovery across the public web",
        lifespan=lifespan,
    )
    app.state.settings = settings

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
    if settings.debug:
        app.include_router(admin.router)

    return app


app = create_app()
