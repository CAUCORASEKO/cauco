import asyncio
import json
from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field

from cauco_core.native_broker import NativeBrokerClient, NativeBrokerUnavailable
from cauco_core.native_broker.wake_events import WakeWordEventService

router = APIRouter()

@router.get("/api/native/wakeword/events")
async def wakeword_events(request: Request) -> StreamingResponse:
    service: WakeWordEventService = request.app.state.wake_event_service
    q, close = service.subscribe()
    async def stream():
        try:
            while not await request.is_disconnected():
                event = await asyncio.to_thread(q.get)
                yield f"event: wakeword.detected\ndata: {json.dumps(event, separators=(',', ':'))}\n\n"
        finally: close()
    return StreamingResponse(stream(), media_type="text/event-stream")

class WakeWordStartRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    phrase_key: str = Field(pattern=r"^hola_cauco$")
    locale: str = Field(pattern=r"^[a-z]{2}(?:-[A-Z]{2})?$")

def wake_result(response: dict[str, object]) -> dict[str, object]:
    result = response.get("result")
    if response.get("outcome") != "success" or not isinstance(result, dict):
        raise NativeBrokerUnavailable("wake word unavailable")
    allowed = {"available", "state", "permission_status", "detector_backend", "phrase_key", "active", "accepted"}
    if set(result) - allowed or any(not isinstance(result.get(k), (str, bool, type(None))) for k in result):
        raise NativeBrokerUnavailable("invalid wake word response")
    return {k: result[k] for k in allowed if k in result}

@router.get("/api/native/wakeword/status")
def wakeword_status(request: Request) -> dict[str, object]:
    client = getattr(request.app.state, "native_broker_client", NativeBrokerClient())
    try: return wake_result(client.wakeword_status())
    except NativeBrokerUnavailable: return {"available": False, "state": "unavailable", "active": False}

@router.post("/api/native/wakeword/start")
def wakeword_start(body: WakeWordStartRequest, request: Request) -> dict[str, object]:
    client = getattr(request.app.state, "native_broker_client", NativeBrokerClient())
    try: return wake_result(client.wakeword_start(body.phrase_key, body.locale))
    except NativeBrokerUnavailable: return {"accepted": False, "available": False, "state": "unavailable", "active": False}

@router.post("/api/native/wakeword/stop")
def wakeword_stop(request: Request) -> dict[str, object]:
    client = getattr(request.app.state, "native_broker_client", NativeBrokerClient())
    try: return wake_result(client.wakeword_stop())
    except NativeBrokerUnavailable: return {"available": False, "state": "unavailable", "active": False}


@router.get("/api/native-broker/status")
def native_broker_status(request: Request) -> dict[str, object]:
    client: NativeBrokerClient = getattr(request.app.state, "native_broker_client", NativeBrokerClient())
    if not client.configured:
        return {"available": False, "configured": False, "status": "unavailable"}
    try:
        response = client.contacts_status()
    except NativeBrokerUnavailable:
        return {"available": False, "configured": True, "status": "unavailable"}
    return {"available": response.get("outcome") == "success", "configured": True, "status": response.get("outcome"), "result": response.get("result")}
