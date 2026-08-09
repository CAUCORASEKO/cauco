from __future__ import annotations
import platform
from typing import Protocol
from cauco_core.connectors.models import PermissionState
from cauco_core.native_broker import NativeBrokerUnavailable, NativeBrokerReferenceNotFound
from .models import CalendarSummary, CalendarEventSummary

class CalendarGateway(Protocol):
    def authorization_state(self) -> PermissionState: ...
    def list(self, limit: int): ...

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
    def list(self, limit: int):
        response = self.client.calendar_list(limit)
        result = response["result"]
        summaries = []
        for item in result["results"]:
            try: summaries.append(CalendarSummary(**item))
            except (TypeError, ValueError) as error: raise NativeBrokerUnavailable("native calendar metadata invalid") from error
        return {**result, "results": summaries}
    def events_range(self, start, end, limit, calendar_reference=None):
        result = self.client.calendar_events_range(start, end, limit, calendar_reference)["result"]
        try: result["results"] = [CalendarEventSummary(**item) for item in result["results"]]
        except (TypeError, ValueError) as error: raise NativeBrokerUnavailable("native calendar events invalid") from error
        return result
    def event_get(self, reference):
        try: result = self.client.calendar_event_get(reference)["result"]
        except NativeBrokerReferenceNotFound as error: raise CalendarEventNotFound from error
        try: return CalendarEventSummary(**result)
        except (TypeError, ValueError) as error: raise NativeBrokerUnavailable("native calendar event invalid") from error
    def event_create(self, **kwargs):
        result = self.client.calendar_event_create(**kwargs)["result"]
        try: return CalendarEventSummary(**result)
        except (TypeError, ValueError) as error: raise NativeBrokerUnavailable("native calendar event invalid") from error

class UnavailableCalendarGateway:
    def authorization_state(self): return PermissionState.UNAVAILABLE
    def event_get(self, reference): raise NativeBrokerUnavailable("native calendar unavailable")

class CalendarEventNotFound(Exception):
    pass
