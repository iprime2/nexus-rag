"""Health endpoints.

Liveness answers one question: "is this process able to respond at all?"
It deliberately checks **no dependencies**. If liveness checked Postgres, a
database outage would make the orchestrator (Docker, ECS) restart every API
container. The restarts can't fix the database; they only add a restart storm
on top of the outage.

Readiness answers "can this instance serve real requests right now?" and
checks every dependency. A failing readiness check (HTTP 503) takes the
instance out of load-balancer rotation *without* killing it. When the
dependency recovers, the next check passes and traffic returns.
"""

from fastapi import APIRouter, Request, Response, status

from app import __version__
from app.api.schemas.health import CheckStatus, LivenessResponse, ReadinessResponse
from app.core.readiness import ReadinessCheck, run_checks

router = APIRouter(prefix="/health", tags=["health"])


@router.get("/live", response_model=LivenessResponse)
async def live() -> LivenessResponse:
    """Report that the process is up and serving requests."""
    return LivenessResponse(version=__version__)


@router.get(
    "/ready",
    response_model=ReadinessResponse,
    responses={503: {"model": ReadinessResponse, "description": "A dependency is not ready"}},
)
async def ready(request: Request, response: Response) -> ReadinessResponse:
    """Check every dependency concurrently; 200 if all are usable, otherwise 503."""
    checks: list[ReadinessCheck] = request.app.state.readiness_checks
    per_check_timeout_s: float = request.app.state.settings.readiness_timeout_seconds

    results = await run_checks(checks, per_check_timeout_s)

    all_ok = all(result.status == "ok" for result in results.values())
    if not all_ok:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return ReadinessResponse(
        status="ready" if all_ok else "not_ready",
        checks={
            name: CheckStatus(status=r.status, latency_ms=r.latency_ms, error=r.error)
            for name, r in results.items()
        },
    )
