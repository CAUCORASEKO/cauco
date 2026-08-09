from typing import Any
from datetime import datetime
from fastapi import APIRouter, HTTPException, Query, Request
from cauco_core.connectors.models import ConnectorRequest
from cauco_core.native_broker import NativeBrokerUnavailable
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

@router.get("/calendars")
def list_calendars(request: Request, limit: int = Query(50, ge=1, le=50), request_id: str = Query(...), requester_id: str = Query(...), explicit_user_request: bool = True):
    runtime_request = ConnectorRequest(request_id, "calendar.calendars.list", None, requester_id, "en", "en", "en", explicit_user_request=explicit_user_request, created_at=datetime.now().astimezone())
    if not request.app.state.connector_runtime.resolve(runtime_request).executable:
        raise HTTPException(status_code=403, detail="Calendar list is not eligible.")
    try: result = request.app.state.apple_calendar_connector.list_calendars(limit)
    except (NativeBrokerUnavailable, ValueError) as error:
        raise HTTPException(status_code=503, detail="Calendar list is unavailable.") from error
    return {**result, "method": "calendar.calendars.list.v1"}
