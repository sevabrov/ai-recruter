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

from app.core.config import Settings, get_settings
from app.db.memory import InMemoryRepository
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


@dataclass
class Container:
    settings: Settings
    seed: SeedData
    repository: Repository
    jobs: JobService
    searches: SearchService
    leads: LeadService
    outreach: OutreachService
    dashboard: DashboardService


def build_container(settings: Settings | None = None) -> Container:
    settings = settings or get_settings()
    seed = load_seed(settings.dev_user_id)
    repository = InMemoryRepository(seed)

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
        repository=repository,
        jobs=jobs,
        searches=searches,
        leads=leads,
        outreach=OutreachService(),
        dashboard=DashboardService(searches, leads, seed),
    )


def get_container(request: Request) -> Container:
    return request.app.state.container


def current_user_id(container: Annotated[Container, Depends(get_container)]) -> str:
    return container.settings.dev_user_id


ContainerDep = Annotated[Container, Depends(get_container)]
UserDep = Annotated[str, Depends(current_user_id)]
