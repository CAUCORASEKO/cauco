from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from cauco_core.perception import (
    PerceptionCapability,
    PerceptionCollectionResult,
    PerceptionHealth,
    PerceptionManager,
    PerceptionRequest,
    PerceptionSourceMetadata,
    PerceptionSourceRegistry,
)

router = APIRouter(prefix="/api/perception", tags=["perception"])

SourceId = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=100),
]


class PerceptionApiModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class PerceptionSourceResponse(PerceptionApiModel):
    metadata: PerceptionSourceMetadata
    health: PerceptionHealth


class PerceptionSourceListResponse(PerceptionApiModel):
    sources: list[PerceptionSourceResponse]
    count: int


class PerceptionCollectRequest(PerceptionApiModel):
    source_ids: list[SourceId] | None = None
    query: str | None = Field(default=None, max_length=500)
    since: datetime | None = None
    limit: int = Field(default=20, ge=1, le=100)
    metadata: dict[str, Any] = Field(default_factory=dict)
    required_capability: PerceptionCapability | None = None

    def to_perception_request(self) -> PerceptionRequest:
        return PerceptionRequest(
            query=self.query,
            since=self.since,
            limit=self.limit,
            metadata=self.metadata,
        )


def perception_registry(request: Request) -> PerceptionSourceRegistry:
    return request.app.state.perception_source_registry


def perception_manager(request: Request) -> PerceptionManager:
    return request.app.state.perception_manager


@router.get("/sources", response_model=PerceptionSourceListResponse)
def list_perception_sources(request: Request) -> PerceptionSourceListResponse:
    sources = [
        PerceptionSourceResponse(
            metadata=source.metadata,
            health=source.health(),
        )
        for source in perception_registry(request).list_sources()
    ]
    return PerceptionSourceListResponse(
        sources=sources,
        count=len(sources),
    )


@router.get(
    "/sources/{source_id}",
    response_model=PerceptionSourceResponse,
)
def get_perception_source(
    source_id: SourceId,
    request: Request,
) -> PerceptionSourceResponse:
    try:
        source = perception_registry(request).get(source_id)
    except KeyError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(error),
        ) from error

    return PerceptionSourceResponse(
        metadata=source.metadata,
        health=source.health(),
    )


@router.get(
    "/sources/{source_id}/health",
    response_model=PerceptionHealth,
)
def get_perception_source_health(
    source_id: SourceId,
    request: Request,
) -> PerceptionHealth:
    try:
        source = perception_registry(request).get(source_id)
    except KeyError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(error),
        ) from error

    return source.health()


@router.post(
    "/collect",
    response_model=PerceptionCollectionResult,
)
def collect_perception(
    payload: PerceptionCollectRequest,
    request: Request,
) -> PerceptionCollectionResult:
    manager = perception_manager(request)
    perception_request = payload.to_perception_request()

    required_capability = payload.required_capability
    if required_capability is None:
        required_capability = (
            PerceptionCapability.SEARCH
            if perception_request.query is not None
            else PerceptionCapability.READ
        )

    try:
        if payload.source_ids is None:
            return manager.collect_all(
                perception_request,
                required_capability=required_capability,
            )

        return manager.collect_many(
            payload.source_ids,
            perception_request,
            required_capability=required_capability,
        )
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(error),
        ) from error
