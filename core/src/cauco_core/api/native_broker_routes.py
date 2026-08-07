from fastapi import APIRouter
from fastapi import Request

from cauco_core.native_broker import NativeBrokerClient, NativeBrokerUnavailable

router = APIRouter()


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
