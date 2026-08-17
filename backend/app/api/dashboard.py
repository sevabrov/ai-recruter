"""Dashboard endpoint (spec §7)."""

from fastapi import APIRouter

from app.api.deps import ContainerDep, UserDep
from app.schemas.dashboard import DashboardOut

router = APIRouter(tags=["dashboard"])


@router.get("/dashboard", response_model=DashboardOut, response_model_exclude_none=True)
async def dashboard(container: ContainerDep, user_id: UserDep) -> DashboardOut:
    return await container.dashboard.get(user_id)
