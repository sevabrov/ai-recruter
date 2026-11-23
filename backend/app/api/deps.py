"""
Composition root and request dependencies.

Everything is built once at startup and hung off `app.state`, so handlers stay
thin and tests can construct the same container without a running server.

`current_user_id` is the authentication seam (spec §55). Until Phase 8 there is
one owner, but every service call already takes a `user_id` and every lookup
is scoped by it — so adding real accounts means replacing this one function, not
auditing every query.
"""

from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncEngine

from app.core.config import Settings, get_settings
from app.db.bootstrap import upgrade_schema_async
from app.db.engine import create_engine, create_session_factory
from app.db.postgres import PostgresRepository
from app.db.repository import Repository
from app.models.lead import Lead
from app.services.adapters import (
    ReaderResources,
    build_brief_parser,
    build_post_reader,
    build_profile_extractor,
    build_reader_resources,
    build_search_provider,
    build_signal_detector,
    use_live_search,
)
from app.services.brief.parser import ResilientBriefParser
from app.services.dashboard.dashboard_service import DashboardService
from app.services.leads.lead_service import LeadService
from app.services.leads.outreach import OutreachService
from app.services.scoring.scoring_service import ScoringService
from app.services.search.pipeline import SearchPipeline
from app.services.search.providers.base import SearchProvider
from app.services.search.query_generator import TemplateQueryGenerator
from app.services.search.search_service import SearchService
from app.workers.job_service import JobService


@dataclass
class Container:
    settings: Settings
    engine: AsyncEngine
    repository: Repository
    provider: SearchProvider
    #: Shared with `POST /searches/estimate`, so the queries the wizard previews
    #: are the queries the worker fires — not a second implementation of them.
    query_generator: TemplateQueryGenerator
    #: None until a ScrapeGraphAI key is configured.
    reader: ReaderResources | None
    #: Reads the client's free-text brief into criteria; rules when no model.
    brief_parser: ResilientBriefParser
    jobs: JobService
    searches: SearchService
    leads: LeadService
    outreach: OutreachService
    dashboard: DashboardService


def build_container(
    settings: Settings | None = None, catalogue: list[Lead] | None = None
) -> Container:
    """
    Wires everything together. Nothing here touches the network: the engine only
    opens connections when a session is used, so building a container is cheap and
    `open_container` owns the part that can fail.

    `catalogue` is what the offline stand-ins (no Brave key) can find. The app
    passes none, so offline searches find no one; the test suite passes its own.
    """
    settings = settings or get_settings()
    engine = create_engine(settings)
    repository = PostgresRepository(create_session_factory(engine))

    scoring = ScoringService()
    query_generator = TemplateQueryGenerator()
    catalogue = catalogue or []

    # The provider is shared by every job on purpose: it owns the connection pool
    # and the per-key rate limiter, neither of which may be duplicated per search.
    # The page reader's sockets and limiter are shared for the same reason, while
    # the extractor around them is per job because its cost counters are.
    provider = build_search_provider(settings, catalogue)
    reader = build_reader_resources(settings)
    post_reader = build_post_reader(settings, reader)
    # Pacing is for the offline stand-ins. Real providers bring their own latency, and
    # adding a quarter of a second per step to it would be nothing but a delay.
    pipeline_settings = (
        settings.model_copy(update={"pipeline_step_delay_ms": 0})
        if use_live_search(settings)
        else settings
    )

    def pipeline_factory() -> SearchPipeline:
        # One pipeline per job: it holds that run's progress and usage counters, and
        # so does its extractor chain — the page reader counts credits per search.
        return SearchPipeline(
            repository=repository,
            settings=pipeline_settings,
            query_generator=query_generator,
            provider=provider,
            extractor=build_profile_extractor(settings, catalogue, repository, reader),
            detector=build_signal_detector(settings),
            scoring=scoring,
            post_reader=post_reader,
        )

    jobs = JobService(repository, pipeline_factory)
    searches = SearchService(repository, jobs)
    leads = LeadService(repository)

    return Container(
        settings=settings,
        engine=engine,
        repository=repository,
        provider=provider,
        query_generator=query_generator,
        reader=reader,
        brief_parser=build_brief_parser(settings),
        jobs=jobs,
        searches=searches,
        leads=leads,
        outreach=OutreachService(),
        dashboard=DashboardService(searches, leads),
    )


async def open_container(
    settings: Settings | None = None, catalogue: list[Lead] | None = None
) -> Container:
    """Build it, bring the schema up to date and make sure the owner row exists."""
    container = build_container(settings, catalogue)
    if container.settings.run_migrations_on_startup:
        await upgrade_schema_async(container.settings.database_url)
    await container.repository.ensure_owner(container.settings.dev_user_id)
    return container


async def close_container(container: Container) -> None:
    """
    In-flight jobs stop first — they are the only thing still using the providers'
    sockets or the database pool — then everything is released.
    """
    await container.jobs.shutdown()
    await container.provider.aclose()
    if container.reader is not None:
        await container.reader.aclose()
    await container.engine.dispose()


def get_container(request: Request) -> Container:
    return request.app.state.container


def current_user_id(container: Annotated[Container, Depends(get_container)]) -> str:
    return container.settings.dev_user_id


ContainerDep = Annotated[Container, Depends(get_container)]
UserDep = Annotated[str, Depends(current_user_id)]
