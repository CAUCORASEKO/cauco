from typing import Any
from fastapi import APIRouter, Request
from cauco_core.connectors.models import PermissionState

router = APIRouter(prefix="/api/apple-calendar", tags=["apple-calendar"])

@router.get("/status")
def connector_status(request: Request) -> dict[str, Any]:
    connector = request.app.state.apple_calendar_connector
    try: state = connector.permissions()[0].state
    except (OSError, RuntimeError, TypeError): state = PermissionState.UNKNOWN
    return {"connector": connector.metadata.connector_id, "provider": connector.metadata.provider_id,
        "registered": True, "availability": connector.metadata.availability.value,
        "permission_state": state.value, "capabilities": list(connector.metadata.capability_ids),
        "method": "calendar.status.v1", "limitations": list(connector.metadata.limitations)}
