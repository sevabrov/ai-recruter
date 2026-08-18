"""
Composition root and request dependencies.

Everything is built once at startup and hung off `app.state`, so handlers stay
thin and tests can construct the same container without a running server.

`current_user_id` is the authentication seam (spec §55). Until Phase 8 there is
one demo owner, but every service call already takes a `user_id` and every lookup
is scoped by it — so adding real accounts means replacing this one function, not
auditing every query.
"""

from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncEngine

from app.core.config import Settings, get_settings
from app.core.logging import get_logger
from app.db.bootstrap import upgrade_schema_async
from app.db.engine import create_engine, create_session_factory
from app.db.postgres import PostgresRepository
from app.db.repository import Repository
from app.db.seed import SeedData, load_seed
from app.services.adapters import (
    build_profile_extractor,
    build_search_provider,
    build_signal_detector,
)
from app.services.dashboard.dashboard_service import DashboardService
from app.services.leads.lead_service import LeadService
from app.services.leads.outreach import OutreachService
from app.services.scoring.scoring_service import ScoringService
from app.services.search.pipeline import SearchPipeline
from app.services.search.query_generator import TemplateQueryGenerator
from app.services.search.search_service import SearchService
from app.workers.job_service import JobService

log = get_logger(__name__)


@dataclass
class Container:
    settings: Settings
    seed: SeedData
    engine: AsyncEngine
    repository: Repository
    jobs: JobService
    searches: SearchService
    leads: LeadService
    outreach: OutreachService
    dashboard: DashboardService


def build_container(settings: Settings | None = None) -> Container:
    """
    Wires everything together. Nothing here touches the network: the engine only
    opens connections when a session is used, so building a container is cheap and
    `open_container` owns the part that can fail.
    """
    settings = settings or get_settings()
    seed = load_seed(settings.dev_user_id)
    engine = create_engine(settings)
    repository = PostgresRepository(create_session_factory(engine), seed)

    scoring = ScoringService()
    query_generator = TemplateQueryGenerator()
    catalogue = seed.catalogue

    def pipeline_factory() -> SearchPipeline:
        # One pipeline per job: it holds that run's progress and usage counters.
        return SearchPipeline(
            repository=repository,
            settings=settings,
            query_generator=query_generator,
            provider=build_search_provider(settings, catalogue),
            extractor=build_profile_extractor(settings, catalogue),
            detector=build_signal_detector(settings),
            scoring=scoring,
        )

    jobs = JobService(repository, pipeline_factory)
    searches = SearchService(repository, jobs)
    leads = LeadService(repository)

    return Container(
        settings=settings,
        seed=seed,
        engine=engine,
        repository=repository,
        jobs=jobs,
        searches=searches,
        leads=leads,
        outreach=OutreachService(),
        dashboard=DashboardService(searches, leads, seed),
    )


async def open_container(settings: Settings | None = None) -> Container:
    """Build it, bring the schema up to date and seed an empty database once."""
    container = build_container(settings)
    if container.settings.run_migrations_on_startup:
        await upgrade_schema_async(container.settings.database_url)
    if await container.repository.ensure_seeded():
        log.info("workspace_seeded")
    return container


async def close_container(container: Container) -> None:
    """In-flight jobs stop first, then the pool is returned to the database."""
    await container.jobs.shutdown()
    await container.engine.dispose()


def get_container(request: Request) -> Container:
    return request.app.state.container


def current_user_id(container: Annotated[Container, Depends(get_container)]) -> str:
    return container.settings.dev_user_id


ContainerDep = Annotated[Container, Depends(get_container)]
UserDep = Annotated[str, Depends(current_user_id)]
