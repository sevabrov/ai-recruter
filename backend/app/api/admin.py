"""
Demo maintenance.

Settings → *Reset demo data* needs somewhere to point once the browser is no
longer the store. Available while `debug` is on; Phase 8 drops it or puts it
behind an admin role.
"""

from fastapi import APIRouter

from app.api.deps import ContainerDep
from app.core.errors import ConflictError
from app.schemas.common import CamelModel

router = APIRouter(prefix="/admin", tags=["admin"])


class ResetOut(CamelModel):
    status: str
    searches: int
    leads: int


@router.post("/reset", response_model=ResetOut)
async def reset(container: ContainerDep) -> ResetOut:
    if not container.settings.debug:
        raise ConflictError("Reset is only available in debug mode")

    # Stop in-flight jobs first, or a running pipeline would write leads back in.
    await container.jobs.shutdown()
    await container.repository.reset()
    return ResetOut(
        status="ok",
        searches=len(container.seed.searches),
        leads=len(container.seed.leads),
    )
