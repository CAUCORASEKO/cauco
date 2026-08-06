"""Read-only application connector matching API."""

from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, Query, Request, status

from cauco_core.application_connector_matching import MatchConfidence, MatchStatus

router = APIRouter(
    prefix="/api/application-connector-matching", tags=["application-connector-matching"]
)


def serialize(value: Any) -> dict[str, Any]:
    return {field: getattr(value, field) for field in value.__dataclass_fields__}


@router.get("/status")
def matching_status(request: Request) -> dict[str, Any]:
    return serialize(request.app.state.application_connector_matching_service.summary())


@router.post("/refresh")
def refresh_matches(request: Request) -> dict[str, Any]:
    request.app.state.application_connector_matching_service.refresh()
    return matching_status(request)


@router.get("/matches")
def list_matches(
    request: Request,
    status_filter: Annotated[MatchStatus | None, Query(alias="status")] = None,
    confidence: MatchConfidence | None = None,
    provider_id: Annotated[str | None, Query(max_length=100)] = None,
    has_registered_connector: bool | None = None,
    connector_available: bool | None = None,
    limit: int = Query(default=100, ge=1, le=100),
) -> dict[str, Any]:
    items = request.app.state.application_connector_matching_service.list(
        status_filter, confidence, provider_id, has_registered_connector, connector_available, limit
    )
    return {
        "matches": [serialize(item) for item in items],
        "count": len(items),
        "method": "application-connector-matching-v1",
        "limitations": ["Permissions and routing are not evaluated."],
    }


@router.get("/matches/{inventory_id}")
def get_match(inventory_id: str, request: Request) -> dict[str, Any]:
    try:
        item = request.app.state.application_connector_matching_service.get(inventory_id)
    except KeyError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Match not found."
        ) from error
    return {"match": serialize(item), "method": item.method, "limitations": list(item.limitations)}


@router.get("/provider-mappings")
def provider_mappings(
    request: Request, limit: int = Query(default=100, ge=1, le=100)
) -> dict[str, Any]:
    items = request.app.state.application_connector_mapping_registry.list(limit)
    return {
        "provider_mappings": [serialize(item) for item in items],
        "count": len(items),
        "method": "application-connector-matching-v1",
        "limitations": ["Mappings do not register or authorize connectors."],
    }
