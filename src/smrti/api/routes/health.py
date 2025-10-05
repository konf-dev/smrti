"""Health check endpoint."""

from fastapi import APIRouter, Depends
from smrti.api.models import HealthCheckResponse
from smrti.api.storage_manager import StorageManager
from smrti.api.dependencies import get_storage_manager
from smrti import __version__

router = APIRouter(tags=["health"])


@router.get(
    "/health",
    response_model=HealthCheckResponse,
    summary="Health check",
    description="Check health status of all system components"
)
async def health_check(
    storage_manager: StorageManager = Depends(get_storage_manager)
) -> HealthCheckResponse:
    """
    Health check endpoint.
    
    Returns status of:
    - Redis (WORKING, SHORT_TERM tiers)
    - Qdrant (LONG_TERM tier)
    - PostgreSQL (EPISODIC, SEMANTIC tiers)
    - Embedding service
    """
    health_data = await storage_manager.health_check()
    
    return HealthCheckResponse(
        status=health_data["status"],
        version=__version__,
        services=health_data["components"]
    )
