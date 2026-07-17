from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Request, status
from pydantic import StringConstraints

from cauco_core.memory.engine import MemoryEngine
from cauco_core.memory.exceptions import (
    InvalidMemoryPathError,
    InvalidSearchQueryError,
    MemoryDirectoryError,
    MemoryFileNotFoundError,
    MemoryFileTooLargeError,
    MemoryFileUnreadableError,
    MemoryPathTraversalError,
)
from cauco_core.memory.models import (
    MemoryEngineStatus,
    MemoryFileContent,
    MemoryFilesResponse,
    MemoryKind,
    MemoryLayer,
    MemoryObject,
    MemoryObjectsResponse,
    MemoryObjectSummary,
    MemorySearchResponse,
)
from cauco_core.memory.search import MemorySearch
from cauco_core.memory.service import MemoryService
from cauco_core.memory_writing.analyzer import MemoryWriteProposalError
from cauco_core.memory_writing.applier import (
    DuplicateMemoryContentError,
    InvalidProposalIntegrityError,
    MemoryWriteApplicationError,
    MemoryWriteProposalApplier,
    MissingApprovedSectionError,
    MissingApprovedTargetError,
)
from cauco_core.memory_writing.models import (
    MemoryWriteApplicationResult,
    MemoryWriteConfirmRequest,
    MemoryWriteOperationsResponse,
    MemoryWriteProposal,
    MemoryWriteRequest,
    StoredMemoryWriteProposal,
)
from cauco_core.memory_writing.proposal_builder import MemoryWriteProposalBuilder
from cauco_core.memory_writing.store import (
    MemoryWriteProposalStore,
    ProposalExpiredError,
    ProposalNotFoundError,
    ProposalStateConflictError,
)

router = APIRouter(prefix="/api/memory", tags=["memory"])
SearchQuery = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)
]
MemoryPath = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]


def memory_service(request: Request) -> MemoryService:
    return request.app.state.memory_service


def memory_search(request: Request) -> MemorySearch:
    return request.app.state.memory_search


def memory_engine(request: Request) -> MemoryEngine:
    return request.app.state.memory_engine


def memory_write_proposal_builder(request: Request) -> MemoryWriteProposalBuilder:
    return request.app.state.memory_write_proposal_builder


def memory_write_proposal_store(request: Request) -> MemoryWriteProposalStore:
    return request.app.state.memory_write_proposal_store


def memory_write_proposal_applier(request: Request) -> MemoryWriteProposalApplier:
    return request.app.state.memory_write_proposal_applier


def memory_error(error: Exception) -> HTTPException:
    if isinstance(error, MemoryFileNotFoundError):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error))
    if isinstance(error, MemoryFileTooLargeError):
        return HTTPException(status_code=status.HTTP_413_CONTENT_TOO_LARGE, detail=str(error))
    if isinstance(error, MemoryFileUnreadableError):
        return HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(error))
    if isinstance(
        error, (InvalidMemoryPathError, MemoryPathTraversalError, InvalidSearchQueryError)
    ):
        return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(error))
    return HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(error))


@router.get("/files", response_model=MemoryFilesResponse)
def list_memory_files(request: Request) -> MemoryFilesResponse:
    try:
        files = memory_service(request).list_markdown_files()
    except MemoryDirectoryError as error:
        raise memory_error(error) from error
    return MemoryFilesResponse(files=files, count=len(files))


@router.get("/file", response_model=MemoryFileContent)
def get_memory_file(request: Request, path: Annotated[MemoryPath, Query()]) -> MemoryFileContent:
    try:
        return memory_service(request).read_file(path)
    except (
        InvalidMemoryPathError,
        MemoryFileNotFoundError,
        MemoryFileTooLargeError,
        MemoryFileUnreadableError,
        MemoryPathTraversalError,
    ) as error:
        raise memory_error(error) from error


@router.get("/search", response_model=MemorySearchResponse)
def search_memory(
    request: Request,
    q: Annotated[SearchQuery, Query()],
    limit: Annotated[int, Query(ge=1, le=20)] = 5,
) -> MemorySearchResponse:
    try:
        results = memory_search(request).search(q, limit)
    except (InvalidSearchQueryError, MemoryDirectoryError) as error:
        raise memory_error(error) from error
    return MemorySearchResponse(query=q, results=results, count=len(results))


@router.get("/engine", response_model=MemoryEngineStatus)
def get_memory_engine(request: Request) -> MemoryEngineStatus:
    return memory_engine(request).status()


@router.get("/objects", response_model=MemoryObjectsResponse)
def list_memory_objects(
    request: Request,
    kind: Annotated[MemoryKind | None, Query()] = None,
    layer: Annotated[MemoryLayer | None, Query()] = None,
) -> MemoryObjectsResponse:
    engine = memory_engine(request)
    objects = engine.list_objects()
    if kind is not None:
        objects = [item for item in objects if item.kind is kind]
    if layer is not None:
        objects = [item for item in objects if item.layer is layer]
    summaries = [MemoryObjectSummary.from_object(item) for item in objects]
    return MemoryObjectsResponse(objects=summaries, count=len(summaries))


@router.get("/objects/{memory_id}", response_model=MemoryObject)
def get_memory_object(request: Request, memory_id: str) -> MemoryObject:
    memory = memory_engine(request).get_object(memory_id)
    if memory is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Memory object not found.",
        )
    return memory


@router.post("/refresh", response_model=MemoryEngineStatus)
def refresh_memory_engine(request: Request) -> MemoryEngineStatus:
    try:
        return memory_engine(request).refresh()
    except MemoryDirectoryError as error:
        raise memory_error(error) from error


@router.post("/write-proposals", response_model=MemoryWriteProposal)
def create_memory_write_proposal(
    payload: MemoryWriteRequest,
    request: Request,
) -> MemoryWriteProposal:
    try:
        proposal = memory_write_proposal_builder(request).build(payload)
        stored = memory_write_proposal_store(request).put(proposal)
        return stored.proposal
    except MemoryWriteProposalError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(error),
        ) from error


@router.get("/write-operations", response_model=MemoryWriteOperationsResponse)
def list_memory_write_operations(request: Request) -> MemoryWriteOperationsResponse:
    operations = memory_write_proposal_builder(request).supported_operations()
    return MemoryWriteOperationsResponse(operations=operations)


@router.get("/write-proposals/{proposal_id}", response_model=StoredMemoryWriteProposal)
def get_memory_write_proposal(
    proposal_id: str,
    request: Request,
) -> StoredMemoryWriteProposal:
    try:
        return memory_write_proposal_store(request).get(proposal_id)
    except ProposalNotFoundError as error:
        raise memory_write_error(error) from error


@router.post(
    "/write-proposals/{proposal_id}/confirm",
    response_model=MemoryWriteApplicationResult,
)
def confirm_memory_write_proposal(
    proposal_id: str,
    payload: MemoryWriteConfirmRequest,
    request: Request,
) -> MemoryWriteApplicationResult:
    if payload.confirm is not True:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Memory write confirmation must be exactly true.",
        )
    try:
        return memory_write_proposal_applier(request).apply(proposal_id)
    except (
        ProposalNotFoundError,
        ProposalExpiredError,
        ProposalStateConflictError,
        InvalidProposalIntegrityError,
        MissingApprovedTargetError,
        MissingApprovedSectionError,
        DuplicateMemoryContentError,
        InvalidMemoryPathError,
        MemoryPathTraversalError,
        MemoryFileNotFoundError,
        MemoryFileTooLargeError,
        MemoryFileUnreadableError,
        MemoryWriteApplicationError,
    ) as error:
        raise memory_write_error(error) from error


def memory_write_error(error: Exception) -> HTTPException:
    if isinstance(error, ProposalNotFoundError):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error))
    if isinstance(error, ProposalExpiredError):
        return HTTPException(status_code=status.HTTP_410_GONE, detail=str(error))
    if isinstance(
        error,
        (
            ProposalStateConflictError,
            MissingApprovedTargetError,
            MissingApprovedSectionError,
            DuplicateMemoryContentError,
        ),
    ):
        return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error))
    if isinstance(
        error,
        (InvalidProposalIntegrityError, InvalidMemoryPathError, MemoryPathTraversalError),
    ):
        return HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(error),
        )
    if isinstance(
        error,
        (MemoryFileNotFoundError, MemoryFileTooLargeError, MemoryFileUnreadableError),
    ):
        return HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="The approved memory target is unavailable or unreadable.",
        )
    return HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="The confirmed memory write could not be completed.",
    )
