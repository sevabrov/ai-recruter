"""Health endpoint (spec §21)."""

from fastapi import APIRouter

from app.api.deps import ContainerDep
from app.schemas.health import HealthOut, ProviderStatus
from app.services.adapters import pipeline_mode

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthOut)
async def health(container: ContainerDep) -> HealthOut:
    settings = container.settings
    return HealthOut(
        status="ok",
        service=settings.app_name,
        version=settings.version,
        phase=settings.phase,
        pipeline=pipeline_mode(settings),
        storage="memory",
        # Booleans only — a key's presence is public, its value never is.
        providers=ProviderStatus(
            brave_search=bool(settings.brave_search_api_key),
            scrapegraph=bool(settings.scrapegraph_api_key),
            openai=bool(settings.openai_api_key),
        ),
    )
