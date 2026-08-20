import json
from collections.abc import Mapping
from dataclasses import asdict
from datetime import UTC, datetime
from time import monotonic
from typing import Any

from cauco_agents import CalendarCreateEventInput, CalendarListEventsInput
from cauco_tools import ToolExecutionError, ToolExecutionRequest, ToolExecutionResult

from cauco_core.connectors.apple_calendar.models import CalendarEventSummary
from cauco_core.connectors.models import PermissionState
from cauco_core.native_broker import NativeBrokerUnavailable


class CalendarToolRuntimeAdapter:
    tool_id = "calendar"
    operations = frozenset({"list_events", "create_event"})

    def __init__(self, connector: Any) -> None:
        self.connector = connector

    def preflight(self, request: ToolExecutionRequest) -> dict[str, object]:
        if request.tool_id != self.tool_id or request.operation_id not in self.operations:
            raise ToolExecutionError("invalid_request", "Calendar operation is invalid.")
        try:
            if request.operation_id == "list_events":
                value = CalendarListEventsInput(**dict(request.arguments))
            else:
                arguments = dict(request.arguments)
                arguments.pop("request_id", None)
                value = CalendarCreateEventInput(**arguments)
        except (TypeError, ValueError) as error:
            raise ToolExecutionError(
                "invalid_arguments", "Calendar arguments are invalid."
            ) from error
        return asdict(value)

    def execute(self, request: ToolExecutionRequest) -> ToolExecutionResult:
        started_at = datetime.now(tz=UTC)
        started = monotonic()
        arguments = self.preflight(request)
        self._require_permission()
        try:
            if request.operation_id == "list_events":
                result = self.connector.events_range(**arguments)
                structured = {
                    "events": tuple(_event_payload(item) for item in result["results"]),
                    "result_count": result["result_count"],
                    "truncated": result["truncated"],
                    "range_start": result["range_start"],
                    "range_end": result["range_end"],
                }
                output = json.dumps(structured, ensure_ascii=False, separators=(",", ":"))
                truncated = len(output) > request.max_output_chars
                output = output[: request.max_output_chars]
                mutation_performed = False
            else:
                request_id = request.arguments.get("request_id")
                if not isinstance(request_id, str) or not request_id.startswith("calendar_create_"):
                    raise ToolExecutionError(
                        "invalid_arguments", "Calendar mutation request ID is invalid."
                    )
                event = self.connector.create_event(request_id, **arguments)
                structured = {"event": _event_payload(event), "verification_passed": True}
                output = "Calendar event created and verified."
                truncated = False
                mutation_performed = True
        except ToolExecutionError:
            raise
        except (NativeBrokerUnavailable, AttributeError, KeyError, TypeError, ValueError) as error:
            raise ToolExecutionError(
                "calendar_unavailable", "Calendar operation is unavailable."
            ) from error
        completed_at = datetime.now(tz=UTC)
        return ToolExecutionResult(
            tool_id=self.tool_id,
            operation_id=request.operation_id,
            success=True,
            started_at=started_at,
            completed_at=completed_at,
            duration_ms=max(0, round((monotonic() - started) * 1000)),
            output=output,
            structured_data=structured,
            truncated=truncated,
            execution_performed=True,
            mutation_performed=mutation_performed,
        )

    def _require_permission(self) -> None:
        try:
            permissions = self.connector.permissions()
            granted = bool(permissions) and permissions[0].state is PermissionState.GRANTED
        except (AttributeError, IndexError, TypeError):
            granted = False
        if not granted:
            raise ToolExecutionError(
                "calendar_permission_denied",
                "Calendar permission is not granted.",
                forbidden=True,
            )


def _event_payload(event: CalendarEventSummary | Mapping[str, object]) -> dict[str, object]:
    if isinstance(event, CalendarEventSummary):
        return asdict(event)
    allowed = {
        "event_reference",
        "calendar_reference",
        "title",
        "start",
        "end",
        "all_day",
        "location",
        "notes",
    }
    if set(event) != allowed:
        raise ToolExecutionError("invalid_response", "Calendar returned invalid event data.")
    try:
        return asdict(CalendarEventSummary(**dict(event)))
    except (TypeError, ValueError) as error:
        raise ToolExecutionError(
            "invalid_response", "Calendar returned invalid event data."
        ) from error
