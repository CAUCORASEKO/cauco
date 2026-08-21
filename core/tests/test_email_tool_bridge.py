from dataclasses import replace
from pathlib import Path

from cauco_agents import (
    AgentPlan,
    AgentPlanStep,
    AgentToolReference,
    EmailDraftInput,
    EmailListMessagesInput,
)
from cauco_tools import ToolExecutionRequest
from fastapi.testclient import TestClient

from cauco_core.agents.review_store import snapshot_digest
from cauco_core.config import Settings
from cauco_core.main import create_app


class FakeBrokerClient:
    configured = True
    token = "t" * 44

    def __init__(self) -> None:
        self.calls: list[dict] = []

    def mail_messages_list(self, limit: int = 20) -> dict:
        self.calls.append(
            {
                "capability": "mail.messages.list",
                "arguments": {"limit": limit},
            }
        )
        return {
            "outcome": "success",
            "result": {
                "results": [
                    {
                        "message_reference": "mailmsg_0123456789abcdef",
                        "sender": "Sender <sender@example.com>",
                        "subject": "Subject",
                        "date_received": "2026-08-21T05:00:00.000Z",
                        "read": False,
                    }
                ],
                "result_count": 1,
                "truncated": False,
            },
            "error": None,
            "limitations": [
                "Inbox only",
                "metadata only",
                "limit 1..20",
                "opaque message references",
                "no body or attachments",
            ],
            "method": "mail.messages.list.v1",
        }

    def request(self, request: dict) -> dict:
        self.calls.append(request)
        arguments = request["arguments"]
        return {
            "outcome": "success",
            "result": {
                "recipient": arguments["recipient"],
                "subject": arguments["subject"],
                "draft_created": True,
            },
            "error": None,
            "limitations": ["draft creation only"],
            "method": "mail.draft.create.v1",
        }


def email_execution(
    client: TestClient,
    operation_input: EmailDraftInput | EmailListMessagesInput,
    *,
    operation_id: str = "draft",
) -> tuple[dict, dict]:
    pending = client.post(
        "/api/agents/plan-reviews",
        json={"instruction": "Inspect git status"},
    ).json()

    store = client.app.state.agent_plan_review_store
    stored = store._records[pending["review_id"]]

    step = AgentPlanStep(
        1,
        "Email draft",
        "Create the approved draft.",
        (),
        "Create through the generic mutation boundary.",
        True,
        False,
        tool_reference=AgentToolReference("email", operation_id),
        operation_input=operation_input,
    )

    plan = AgentPlan(
        agent_id=stored.plan.agent_id,
        agent_name=stored.plan.agent_name,
        status=stored.plan.status,
        objective="Exercise the email tool bridge.",
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

    store._records[stored.review_id] = replace(
        stored,
        plan=plan,
        snapshot_digest=digest,
    )

    approved = client.post(
        f"/api/agents/plan-reviews/{stored.review_id}/approve",
        json={},
    )
    execution = client.post(
        "/api/executions",
        json={"review_id": approved.json()["review_id"]},
    )

    assert approved.status_code == 200
    assert execution.status_code == 201

    return approved.json(), execution.json()


def test_email_list_messages_adapter_is_read_only_and_bounded(tmp_path: Path) -> None:
    brain = tmp_path / "brain"
    brain.mkdir()

    with TestClient(create_app(Settings(brain_dir=brain))) as client:
        adapter = client.app.state.tool_adapter_registry.get(
            "email",
            "list_messages",
        )
        fake = FakeBrokerClient()
        adapter.broker_client = fake

        request = ToolExecutionRequest(
            "email",
            "list_messages",
            {"limit": 5},
        )

        inspected = adapter.preflight(request)

        assert inspected == {"limit": 5}
        assert fake.calls == []

        result = adapter.execute(request)

        assert result.success is True
        assert result.execution_performed is True
        assert result.mutation_performed is False
        assert result.structured_data["result_count"] == 1
        assert result.structured_data["truncated"] is False
        assert len(result.structured_data["messages"]) == 1

        message = result.structured_data["messages"][0]

        assert message == {
            "message_reference": "mailmsg_0123456789abcdef",
            "sender": "Sender <sender@example.com>",
            "subject": "Subject",
            "date_received": "2026-08-21T05:00:00.000Z",
            "read": False,
        }

        assert fake.calls == [
            {
                "capability": "mail.messages.list",
                "arguments": {"limit": 5},
            }
        ]


def test_email_list_messages_runs_through_execution_service_without_workspace(
    tmp_path: Path,
) -> None:
    brain = tmp_path / "brain"
    brain.mkdir()

    with TestClient(create_app(Settings(brain_dir=brain))) as client:
        adapter = client.app.state.tool_adapter_registry.get(
            "email",
            "list_messages",
        )
        fake = FakeBrokerClient()
        adapter.broker_client = fake

        approved, execution = email_execution(
            client,
            EmailListMessagesInput(limit=5),
            operation_id="list_messages",
        )

        execution_id = execution["execution_id"]

        run = client.post(
            f"/api/executions/{execution_id}/run",
        )

        assert run.status_code == 200

        payload = run.json()

        assert payload["state"] == "completed"

        record_response = client.get(
            f"/api/executions/{execution_id}",
        )

        assert record_response.status_code == 200

        record = record_response.json()
        assert record["status"] == "completed"

        result = record["step_records"][0]["result"]

        assert result["success"] is True
        assert result["execution_performed"] is True
        assert result["mutation_performed"] is False
        assert result["structured_data"]["result_count"] == 1
        assert result["structured_data"]["truncated"] is False

        assert fake.calls == [
            {
                "capability": "mail.messages.list",
                "arguments": {"limit": 5},
            }
        ]

        refreshed = client.get(f"/api/agents/plan-reviews/{approved['review_id']}").json()

        assert refreshed["plan"] == approved["plan"]
        assert refreshed["snapshot_digest"] == approved["snapshot_digest"]


def test_email_agent_inbox_plan_runs_unchanged_through_task_runtime(
    tmp_path: Path,
) -> None:
    brain = tmp_path / "brain"
    brain.mkdir()

    with TestClient(create_app(Settings(brain_dir=brain))) as client:
        adapter = client.app.state.tool_adapter_registry.get(
            "email",
            "list_messages",
        )
        fake = FakeBrokerClient()
        adapter.broker_client = fake

        pending_response = client.post(
            "/api/agents/plan-reviews",
            json={
                "instruction": "Muéstrame los últimos 5 correos",
                "include_context": False,
            },
        )

        assert pending_response.status_code == 201
        pending = pending_response.json()
        assert pending["selected_agent_id"] == "email"
        assert pending["readiness"]["ready"] is True
        assert pending["plan"]["requires_confirmation"] is False
        assert pending["plan"]["metadata"]["skill_id"] == "email.inspect_inbox"
        assert len(pending["plan"]["steps"]) == 1

        step = pending["plan"]["steps"][0]
        assert step["tool_reference"] == {
            "tool_id": "email",
            "operation_id": "list_messages",
            "target": None,
        }
        assert step["operation_input"] == {"limit": 5}
        assert step["requires_confirmation"] is False
        assert fake.calls == []

        approved_response = client.post(
            f"/api/agents/plan-reviews/{pending['review_id']}/approve",
            json={},
        )
        assert approved_response.status_code == 200
        approved = approved_response.json()

        execution_response = client.post(
            "/api/executions",
            json={"review_id": approved["review_id"]},
        )
        assert execution_response.status_code == 201
        execution_id = execution_response.json()["execution_id"]

        run_response = client.post(f"/api/executions/{execution_id}/run")
        assert run_response.status_code == 200
        assert run_response.json()["state"] == "completed"
        assert fake.calls == [
            {
                "capability": "mail.messages.list",
                "arguments": {"limit": 5},
            }
        ]

        repeated_run = client.post(f"/api/executions/{execution_id}/run")
        assert repeated_run.status_code == 200
        assert repeated_run.json()["state"] == "completed"
        assert fake.calls == [
            {
                "capability": "mail.messages.list",
                "arguments": {"limit": 5},
            }
        ]

        refreshed = client.get(
            f"/api/agents/plan-reviews/{approved['review_id']}"
        ).json()
        assert refreshed["plan"] == approved["plan"]
        assert refreshed["snapshot_digest"] == approved["snapshot_digest"]


def test_email_adapter_preflight_is_inert_and_execution_is_typed(tmp_path: Path) -> None:
    brain = tmp_path / "brain"
    brain.mkdir()

    with TestClient(create_app(Settings(brain_dir=brain))) as client:
        adapter = client.app.state.tool_adapter_registry.get("email", "draft")
        fake = FakeBrokerClient()
        adapter.broker_client = fake

        request = ToolExecutionRequest(
            "email",
            "draft",
            {
                "recipient": "claudio@aisosu.fi",
                "subject": "Prueba",
                "body": "Contenido",
                "request_id": "email_draft_0123456789abcdef01234567",
            },
        )

        inspected = adapter.preflight(request)

        assert inspected == {
            "recipient": "claudio@aisosu.fi",
            "subject": "Prueba",
            "body": "Contenido",
        }
        assert fake.calls == []

        result = adapter.execute(request)

        assert result.success is True
        assert result.mutation_performed is True
        assert result.structured_data["draft_created"] is True
        assert result.structured_data["verification_passed"] is True
        assert len(fake.calls) == 1
        assert fake.calls[0]["capability"] == "mail.draft.create"


def test_email_preflight_rejects_payload_larger_than_broker_transport(
    tmp_path: Path,
) -> None:
    brain = tmp_path / "brain"
    brain.mkdir()

    with TestClient(create_app(Settings(brain_dir=brain))) as client:
        adapter = client.app.state.tool_adapter_registry.get("email", "draft")
        fake = FakeBrokerClient()
        adapter.broker_client = fake

        request = ToolExecutionRequest(
            "email",
            "draft",
            {
                "recipient": "claudio@aisosu.fi",
                "subject": "Prueba",
                "body": "😀" * 4_000,
            },
        )

        try:
            adapter.preflight(request)
        except Exception as error:
            assert getattr(error, "code", None) == "request_too_large"
        else:
            raise AssertionError("Oversized email broker payload was accepted.")

        assert fake.calls == []


def test_email_draft_is_preview_first_and_single_use(tmp_path: Path) -> None:
    brain = tmp_path / "brain"
    brain.mkdir()

    with TestClient(create_app(Settings(brain_dir=brain))) as client:
        adapter = client.app.state.tool_adapter_registry.get("email", "draft")
        fake = FakeBrokerClient()
        adapter.broker_client = fake

        approved, execution = email_execution(
            client,
            EmailDraftInput(
                "claudio@aisosu.fi",
                "Prueba Cauco",
                "Este borrador no debe enviarse.",
            ),
        )

        execution_id = execution["execution_id"]

        paused = client.post(f"/api/executions/{execution_id}/run")

        assert paused.status_code == 200
        assert paused.json()["state"] == "awaiting_confirmation"
        assert fake.calls == []

        preview = client.get(f"/api/executions/{execution_id}/steps/1/mutation-preview").json()

        assert preview["confirmation_phrase"] == "PREPARE EMAIL DRAFT"
        assert preview["target"] == "claudio@aisosu.fi"
        assert preview["proposed_after_state"]["draft_created"] is True
        assert preview["proposed_after_state"]["sent"] is False
        assert preview["normalized_arguments"]["request_id"].startswith("email_draft_")
        assert len(preview["normalized_arguments"]["request_id"]) <= 64
        assert fake.calls == []

        confirmation = {
            "preview_id": preview["preview_id"],
            "preview_digest": preview["preview_digest"],
            "confirmation_phrase": preview["confirmation_phrase"],
        }

        confirmed = client.post(
            f"/api/executions/{execution_id}/steps/1/confirm-mutation",
            json=confirmation,
        )
        repeated = client.post(
            f"/api/executions/{execution_id}/steps/1/confirm-mutation",
            json=confirmation,
        )

        refreshed = client.get(f"/api/agents/plan-reviews/{approved['review_id']}").json()

        assert confirmed.status_code == 200
        assert confirmed.json()["status"] == "completed"

        result = confirmed.json()["step_records"][0]["result"]
        assert result["success"] is True
        assert result["mutation_performed"] is True
        assert result["structured_data"]["draft_created"] is True

        assert repeated.status_code == 409
        assert len(fake.calls) == 1

        assert refreshed["plan"] == approved["plan"]
        assert refreshed["snapshot_digest"] == approved["snapshot_digest"]
