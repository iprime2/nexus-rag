"""Health endpoints.

Liveness answers one question: "is this process able to respond at all?"
It deliberately checks **no dependencies**. If liveness checked Postgres, a
database outage would make the orchestrator (Docker, ECS) restart every API
container. The restarts can't fix the database; they only add a restart storm
on top of the outage.

Dependency checks belong in readiness (``/health/ready``, step 1.6). A failing
readiness check takes the instance out of load-balancer rotation without
killing it.
"""

from fastapi import APIRouter

from app import __version__
from app.api.schemas.health import LivenessResponse

router = APIRouter(prefix="/health", tags=["health"])


@router.get("/live", response_model=LivenessResponse)
async def live() -> LivenessResponse:
    """Report that the process is up and serving requests."""
    return LivenessResponse(version=__version__)
