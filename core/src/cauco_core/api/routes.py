from fastapi import APIRouter, HTTPException, Request, status

from cauco_core.schemas import HealthResponse, MemoryFilesResponse, SystemStatusResponse
from cauco_core.services.memory_service import MemoryDirectoryError, MemoryService
from cauco_core.services.status_service import StatusService

router = APIRouter()


def memory_service(request: Request) -> MemoryService:
    return MemoryService(request.app.state.settings.resolved_brain_dir())


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse()


@router.get("/api/status", response_model=SystemStatusResponse)
def system_status(request: Request) -> SystemStatusResponse:
    try:
        return StatusService(memory_service(request)).get_status()
    except MemoryDirectoryError as error:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(error)
        ) from error


@router.get("/api/memory/files", response_model=MemoryFilesResponse)
def memory_files(request: Request) -> MemoryFilesResponse:
    try:
        files = memory_service(request).list_markdown_files()
    except MemoryDirectoryError as error:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(error)
        ) from error
    return MemoryFilesResponse(files=files, count=len(files))
