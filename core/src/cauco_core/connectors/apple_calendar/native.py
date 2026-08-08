from __future__ import annotations
import platform
from typing import Protocol
from cauco_core.connectors.models import PermissionState
from cauco_core.native_broker import NativeBrokerUnavailable

class CalendarGateway(Protocol):
    def authorization_state(self) -> PermissionState: ...

class BrokerCalendarGateway:
    def __init__(self, client): self.client = client
    def authorization_state(self) -> PermissionState:
        try:
            state = self.client.calendar_status()["result"]["state"]
            return {"granted": PermissionState.GRANTED, "notRequested": PermissionState.NOT_REQUESTED,
                    "denied": PermissionState.DENIED, "restricted": PermissionState.RESTRICTED,
                    "unavailable": PermissionState.UNAVAILABLE}[state]
        except (NativeBrokerUnavailable, KeyError, TypeError, ValueError):
            return PermissionState.UNAVAILABLE

class UnavailableCalendarGateway:
    def authorization_state(self): return PermissionState.UNAVAILABLE
