from dataclasses import replace
from pathlib import Path

import pytest
from cauco_agents import (
    AgentPlan,
    AgentPlanStep,
    AgentToolReference,
    CalendarCreateEventInput,
    CalendarListEventsInput,
)
from cauco_tools import ToolExecutionError, ToolExecutionRequest
from fastapi.testclient import TestClient

from cauco_core.agents.review_store import snapshot_digest
from cauco_core.config import Settings
from cauco_core.connectors.apple_calendar.models import CalendarEventSummary
from cauco_core.connectors.apple_calendar.permissions import permission_definition
from cauco_core.connectors.apple_calendar.tool_adapter import CalendarToolRuntimeAdapter
from cauco_core.connectors.models import PermissionState
from cauco_core.main import create_app

START = "2026-08-21T10:00:00+03:00"
END = "2026-08-21T11:00:00+03:00"
CALENDAR_REFERENCE = "calendar_abcdefgh"
EVENT_REFERENCE = "event_abcdefgh"


class FakeCalendarConnector:
    def __init__(self, permission: PermissionState = PermissionState.GRANTED) -> None:
        self.permission = permission
        self.list_calls = 0
        self.create_calls = 0

    def permissions(self):
        return (permission_definition(self.permission),)

    def events_range(self, **arguments):
        self.list_calls += 1
        event = CalendarEventSummary(
            EVENT_REFERENCE,
            CALENDAR_REFERENCE,
            "Planning",
            START,
            END,
            False,
            "",
            "",
        )
        return {
            "results": [event],
            "result_count": 1,
            "truncated": False,
            "range_start": arguments["start"],
            "range_end": arguments["end"],
        }

    def create_event(self, request_id: str, **arguments):
        assert request_id.startswith("calendar_create_")
        self.create_calls += 1
        return CalendarEventSummary(
            EVENT_REFERENCE,
            arguments.get("calendar_reference") or CALENDAR_REFERENCE,
            arguments["title"],
            arguments["start"],
            arguments["end"],
            arguments["all_day"],
            arguments.get("location") or "",
            arguments.get("notes") or "",
        )


def test_calendar_adapter_lists_events_and_enforces_native_permission() -> None:
    connector = FakeCalendarConnector()
    adapter = CalendarToolRuntimeAdapter(connector)
    request = ToolExecutionRequest(
        "calendar",
        "list_events",
        {"start": START, "end": END, "limit": 10, "calendar_reference": None},
    )

    result = adapter.execute(request)

    assert result.success is True
    assert result.mutation_performed is False
    assert result.structured_data["result_count"] == 1
    assert result.structured_data["events"][0]["event_reference"] == EVENT_REFERENCE
    assert connector.list_calls == 1

    denied = CalendarToolRuntimeAdapter(FakeCalendarConnector(PermissionState.DENIED))
    with pytest.raises(ToolExecutionError) as caught:
        denied.execute(request)
    assert caught.value.code == "calendar_permission_denied"
    assert caught.value.forbidden is True


def test_calendar_create_preflight_is_inert_and_execution_is_typed() -> None:
    connector = FakeCalendarConnector()
    adapter = CalendarToolRuntimeAdapter(connector)
    arguments = {
        "title": "Planning",
        "start": START,
        "end": END,
        "all_day": False,
        "calendar_reference": CALENDAR_REFERENCE,
        "location": None,
        "notes": None,
        "request_id": "calendar_create_abcdefghijkl",
    }
    request = ToolExecutionRequest("calendar", "create_event", arguments)

    inspected = adapter.preflight(request)
    assert inspected["title"] == "Planning"
    assert connector.create_calls == 0

    result = adapter.execute(request)
    assert result.success is True
    assert result.mutation_performed is True
    assert result.structured_data["verification_passed"] is True
    assert connector.create_calls == 1


def calendar_execution(
    client: TestClient, operation_input: CalendarListEventsInput | CalendarCreateEventInput
) -> tuple[dict, dict]:
    pending = client.post(
        "/api/agents/plan-reviews", json={"instruction": "Inspect git status"}
    ).json()
    store = client.app.state.agent_plan_review_store
    stored = store._records[pending["review_id"]]
    operation_id = (
        "list_events" if isinstance(operation_input, CalendarListEventsInput) else "create_event"
    )
    step = AgentPlanStep(
        1,
        "Calendar operation",
        "Use the approved typed calendar operation.",
        (),
        "Run through the generic tool boundary.",
        operation_id == "create_event",
        False,
        tool_reference=AgentToolReference("calendar", operation_id),
        operation_input=operation_input,
    )
    plan = AgentPlan(
        agent_id=stored.plan.agent_id,
        agent_name=stored.plan.agent_name,
        status=stored.plan.status,
        objective="Exercise the calendar tool bridge.",
        context_used=stored.plan.context_used,
        steps=(step,),
        open_questions=(),
        warnings=stored.plan.warnings,
        requires_confirmation=True,
        metadata=stored.plan.metadata,
    )
    digest = snapshot_digest(
        instruction=stored.instruction,
        selected_agent_id=stored.selected_agent_id,
        routing=stored.routing,
        context=stored.context,
        plan=plan,
    )
    store._records[stored.review_id] = replace(stored, plan=plan, snapshot_digest=digest)
    approved = client.post(f"/api/agents/plan-reviews/{stored.review_id}/approve", json={})
    execution = client.post(
        "/api/executions", json={"review_id": approved.json()["review_id"]}
    )
    assert approved.status_code == 200
    assert execution.status_code == 201
    return approved.json(), execution.json()


@pytest.fixture
def calendar_client(tmp_path: Path):
    brain = tmp_path / "brain"
    brain.mkdir()
    with TestClient(create_app(Settings(brain_dir=brain))) as client:
        connector = FakeCalendarConnector()
        adapter = client.app.state.tool_adapter_registry.get("calendar", "list_events")
        adapter.connector = connector
        yield client, connector


def test_calendar_list_runs_only_through_execution_service(calendar_client) -> None:
    client, connector = calendar_client
    approved, execution = calendar_execution(
        client, CalendarListEventsInput(START, END, 10)
    )

    result = client.post(
        f"/api/executions/{execution['execution_id']}/steps/1/execute", json={}
    )
    refreshed = client.get(f"/api/agents/plan-reviews/{approved['review_id']}").json()

    assert result.status_code == 200
    assert result.json()["status"] == "completed"
    assert result.json()["step_records"][0]["result"]["structured_data"]["result_count"] == 1
    assert connector.list_calls == 1
    assert refreshed["snapshot_digest"] == approved["snapshot_digest"]
    assert refreshed["plan"] == approved["plan"]


def test_calendar_create_is_preview_first_single_use_and_runtime_resumable(
    calendar_client,
) -> None:
    client, connector = calendar_client
    approved, execution = calendar_execution(
        client,
        CalendarCreateEventInput(
            "Planning",
            START,
            END,
            False,
            CALENDAR_REFERENCE,
            "Room 1",
            "Approved agenda",
        ),
    )

    paused = client.post(f"/api/executions/{execution['execution_id']}/run")
    assert paused.status_code == 200
    assert paused.json()["state"] == "awaiting_confirmation"
    assert connector.create_calls == 0

    preview = client.get(
        f"/api/executions/{execution['execution_id']}/steps/1/mutation-preview"
    ).json()
    assert preview["confirmation_phrase"] == "CREATE CALENDAR EVENT"
    assert "Planning" in preview["diff_preview"]
    assert connector.create_calls == 0

    confirmed = client.post(
        f"/api/executions/{execution['execution_id']}/steps/1/confirm-mutation",
        json={
            "preview_id": preview["preview_id"],
            "preview_digest": preview["preview_digest"],
            "confirmation_phrase": preview["confirmation_phrase"],
        },
    )
    repeated = client.post(
        f"/api/executions/{execution['execution_id']}/steps/1/confirm-mutation",
        json={
            "preview_id": preview["preview_id"],
            "preview_digest": preview["preview_digest"],
            "confirmation_phrase": preview["confirmation_phrase"],
        },
    )
    refreshed = client.get(f"/api/agents/plan-reviews/{approved['review_id']}").json()

    assert confirmed.status_code == 200
    assert confirmed.json()["status"] == "completed"
    assert confirmed.json()["step_records"][0]["result"]["mutation_performed"] is True
    assert repeated.status_code == 409
    assert connector.create_calls == 1
    assert refreshed["plan"] == approved["plan"]
    assert refreshed["snapshot_digest"] == approved["snapshot_digest"]


def test_calendar_mutation_permission_failure_is_consumed_and_never_retried(
    calendar_client,
) -> None:
    client, connector = calendar_client
    connector.permission = PermissionState.DENIED
    _, execution = calendar_execution(
        client,
        CalendarCreateEventInput("Planning", START, END, False),
    )
    paused = client.post(f"/api/executions/{execution['execution_id']}/run").json()
    preview = client.get(
        f"/api/executions/{execution['execution_id']}/steps/1/mutation-preview"
    ).json()

    confirmed = client.post(
        f"/api/executions/{execution['execution_id']}/steps/1/confirm-mutation",
        json={
            "preview_id": preview["preview_id"],
            "preview_digest": preview["preview_digest"],
            "confirmation_phrase": preview["confirmation_phrase"],
        },
    )
    resumed = client.post(f"/api/executions/{execution['execution_id']}/resume")

    assert paused["state"] == "awaiting_confirmation"
    assert confirmed.status_code == 200
    assert confirmed.json()["status"] == "failed"
    assert confirmed.json()["step_records"][0]["result"]["error_code"] == (
        "calendar_permission_denied"
    )
    assert resumed.json()["state"] == "failed"
    assert connector.create_calls == 0
