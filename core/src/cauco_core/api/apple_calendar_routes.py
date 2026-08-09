from typing import Any
from datetime import datetime
from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field
from cauco_core.connectors.models import ConnectorRequest
from cauco_core.native_broker import NativeBrokerUnavailable
from cauco_core.connectors.apple_calendar.native import CalendarEventNotFound
from cauco_core.connectors.models import PermissionState

router = APIRouter(prefix="/api/apple-calendar", tags=["apple-calendar"])
class CreateEventRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(min_length=1, max_length=300); start: str; end: str; all_day: bool
    calendar_reference: str | None = None; location: str | None = Field(None, max_length=300); notes: str | None = Field(None, max_length=1000)
    request_id: str = Field(min_length=1, max_length=100); requester_id: str = Field(min_length=1, max_length=100)
    request_locale: str = "en"; response_locale: str = "en"; interface_locale: str = "en"; explicit_user_request: bool = False; confirmation_request_id: str | None = None

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

@router.get("/events")
def list_events(request: Request, start: str = Query(...), end: str = Query(...), limit: int = Query(100, ge=1, le=100), calendar_reference: str | None = Query(None), request_id: str = Query(...), requester_id: str = Query(...), explicit_user_request: bool = True):
    runtime_request = ConnectorRequest(request_id, "calendar.events.range", None, requester_id, "en", "en", "en", explicit_user_request=explicit_user_request, created_at=datetime.now().astimezone())
    if not request.app.state.connector_runtime.resolve(runtime_request).executable: raise HTTPException(status_code=403, detail="Calendar event range is not eligible.")
    try: result = request.app.state.apple_calendar_connector.events_range(start, end, limit, calendar_reference)
    except (NativeBrokerUnavailable, ValueError) as error: raise HTTPException(status_code=503, detail="Calendar event range is unavailable.") from error
    return {**result, "method": "calendar.events.range.v1"}

@router.get("/events/{event_reference}")
def get_event(event_reference: str, request: Request, request_id: str = Query(...), requester_id: str = Query(...), explicit_user_request: bool = True):
    runtime_request = ConnectorRequest(request_id, "calendar.events.get", None, requester_id, "en", "en", "en", explicit_user_request=explicit_user_request, created_at=datetime.now().astimezone())
    if not request.app.state.connector_runtime.resolve(runtime_request).executable: raise HTTPException(status_code=403, detail="Calendar event get is not eligible.")
    try: event = request.app.state.apple_calendar_connector.get_event(event_reference)
    except CalendarEventNotFound as error: raise HTTPException(status_code=404, detail="Calendar event is unavailable.") from error
    except ValueError as error: raise HTTPException(status_code=422, detail="Invalid calendar event reference.") from error
    except NativeBrokerUnavailable as error: raise HTTPException(status_code=503, detail="Calendar event is unavailable.") from error
    return {"event": {field: getattr(event, field) for field in event.__dataclass_fields__}, "method": "calendar.events.get.v1"}

@router.post("/events")
def create_event(payload: CreateEventRequest, request: Request):
    runtime_request = ConnectorRequest(payload.request_id, "calendar.events.create", None, payload.requester_id, payload.request_locale, payload.response_locale, payload.interface_locale, explicit_user_request=payload.explicit_user_request, confirmation_request_id=payload.confirmation_request_id, created_at=datetime.now().astimezone())
    routing = request.app.state.connector_runtime.resolve(runtime_request)
    if not routing.executable: raise HTTPException(status_code=403, detail="Calendar event creation requires an explicit confirmed request.")
    try: event = request.app.state.apple_calendar_connector.create_event(payload.request_id, title=payload.title, start=payload.start, end=payload.end, all_day=payload.all_day, calendar_reference=payload.calendar_reference, location=payload.location, notes=payload.notes)
    except ValueError as error: raise HTTPException(status_code=422, detail="Invalid calendar event request.") from error
    except NativeBrokerUnavailable as error: raise HTTPException(status_code=503, detail="Calendar event creation is unavailable.") from error
    return {"event": {field: getattr(event, field) for field in event.__dataclass_fields__}, "method": "calendar.events.create.v1"}
