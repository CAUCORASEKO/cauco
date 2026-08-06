"""Read-only application inventory API."""

from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request, status

from cauco_core.application_inventory.exceptions import ApplicationNotFoundError
from cauco_core.application_inventory.models import ApplicationAvailability, ApplicationSource

router = APIRouter(prefix="/api/application-inventory", tags=["application-inventory"])


def _item(item: Any) -> dict[str, Any]:
    return {field: getattr(item, field) for field in item.__dataclass_fields__}


@router.get("/status")
def inventory_status(request: Request) -> dict[str, Any]:
    result = request.app.state.application_inventory_service.status()
    return {field: getattr(result, field) for field in result.__dataclass_fields__}


@router.post("/refresh")
def refresh_inventory(request: Request) -> dict[str, Any]:
    request.app.state.application_inventory_service.refresh()
    return inventory_status(request)


@router.get("/applications")
def list_applications(
    request: Request,
    source: ApplicationSource | None = None,
    availability: ApplicationAvailability | None = None,
    architecture: str | None = Query(default=None, max_length=20),
    bundle_identifier: str | None = Query(default=None, max_length=200),
    query: str | None = Query(default=None, max_length=200),
    limit: int = Query(default=100, ge=1, le=100),
) -> dict[str, Any]:
    items = request.app.state.application_inventory_service.list(
        source, availability, architecture, bundle_identifier, query, limit
    )
    return {
        "applications": [_item(item) for item in items],
        "count": len(items),
        "method": "mac-application-inventory-v1",
        "limitations": ["Metadata inspection only; no application action is performed."],
    }


@router.get("/applications/{inventory_id}")
def get_application(inventory_id: str, request: Request) -> dict[str, Any]:
    try:
        item = request.app.state.application_inventory_service.get(inventory_id)
    except ApplicationNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Application not found."
        ) from error
    return {
        "application": _item(item),
        "method": "mac-application-inventory-v1",
        "limitations": list(item.limitations),
    }
