from fastapi import APIRouter, HTTPException, Request, status

from cauco_core.schemas import HealthResponse, SystemStatusResponse
from cauco_core.services.memory_service import MemoryDirectoryError
from cauco_core.services.status_service import StatusService

router = APIRouter()


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse()


@router.get("/api/status", response_model=SystemStatusResponse)
def system_status(request: Request) -> SystemStatusResponse:
    try:
        return StatusService(
            request.app.state.memory_service,
            registered_agents=len(request.app.state.agent_registry),
        ).get_status()
    except MemoryDirectoryError as error:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(error)
        ) from error
