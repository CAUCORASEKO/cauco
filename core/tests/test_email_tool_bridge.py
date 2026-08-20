from dataclasses import replace
from pathlib import Path

from cauco_agents import (
    AgentPlan,
    AgentPlanStep,
    AgentToolReference,
    EmailDraftInput,
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


def email_execution(client: TestClient, operation_input: EmailDraftInput) -> tuple[dict, dict]:
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
        tool_reference=AgentToolReference("email", "draft"),
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
