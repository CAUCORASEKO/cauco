from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime
from pathlib import Path

import pytest
from cauco_agents import (
    AgentPlan,
    AgentPlanStep,
    AgentToolReference,
    EmailListAccountsInput,
    EmailListMailboxesInput,
    StepOutputBinding,
)
from cauco_tools import ToolExecutionRequest, ToolExecutionResult
from fastapi.testclient import TestClient

from cauco_core.agents.review_store import snapshot_digest
from cauco_core.config import Settings
from cauco_core.connectors.apple_mail.tool_adapter import EmailToolRuntimeAdapter
from cauco_core.execution.bindings import (
    StepOutputBindingError,
    resolve_step_output_bindings,
)
from cauco_core.execution.models import (
    AgentPlanExecutionRecord,
    AgentPlanStepExecutionRecord,
    ExecutionStatus,
    StepExecutionStatus,
)
from cauco_core.main import create_app


@dataclass(frozen=True, slots=True)
class GenericBoundInput:
    reference: str | StepOutputBinding

    def __post_init__(self) -> None:
        if not isinstance(self.reference, (str, StepOutputBinding)):
            raise ValueError("Reference must be a string or binding.")


def result(data: dict, *, success: bool = True) -> ToolExecutionResult:
    now = datetime.now(tz=UTC)
    return ToolExecutionResult(
        tool_id="generic",
        operation_id="read",
        success=success,
        started_at=now,
        completed_at=now,
        duration_ms=0,
        output="",
        structured_data=data,
        error_code=None if success else "read_failed",
        error_message=None if success else "Read failed safely.",
    )


def execution_record(
    data: dict,
    *,
    source_status: StepExecutionStatus = StepExecutionStatus.COMPLETED,
    source_result: ToolExecutionResult | None = None,
) -> AgentPlanExecutionRecord:
    actual_source_result = (
        None
        if source_status is StepExecutionStatus.PENDING and source_result is None
        else source_result
        if source_result is not None
        else result(data)
    )
    return AgentPlanExecutionRecord(
        execution_id="exec_abcdefghijklmnopqrstuvwx",
        review_id="planrev_abcdefghijklmnopqrstuvwx",
        snapshot_digest="0" * 64,
        status=ExecutionStatus.RUNNING,
        created_at=datetime.now(tz=UTC),
        started_at=datetime.now(tz=UTC),
        completed_at=None,
        current_step_index=None,
        total_steps=2,
        step_records=(
            AgentPlanStepExecutionRecord(
                step_index=1,
                tool_id="generic",
                operation_id="read",
                target=None,
                status=source_status,
                result=actual_source_result,
                execution_performed=source_status is not StepExecutionStatus.PENDING,
            ),
            AgentPlanStepExecutionRecord(
                step_index=2,
                tool_id="generic",
                operation_id="consume",
                target=None,
                status=StepExecutionStatus.PENDING,
            ),
        ),
        execution_performed=True,
        failure_reason=None,
        audit_events=(),
    )


def resolve(data: dict, path: tuple[str | int, ...]) -> object:
    operation_input = GenericBoundInput(StepOutputBinding(1, path))
    resolved, _ = resolve_step_output_bindings(
        operation_input,
        record=execution_record(data),
        consuming_step_index=2,
    )
    return resolved


def test_literal_operation_input_remains_the_same_object() -> None:
    operation_input = GenericBoundInput("literal-reference")

    resolved, resolutions = resolve_step_output_bindings(
        operation_input,
        record=execution_record({"reference": "ignored"}),
        consuming_step_index=2,
    )

    assert resolved is operation_input
    assert resolutions == ()


def test_binding_consumes_scalar_string_from_prior_structured_data() -> None:
    assert resolve({"reference": "opaque-reference"}, ("reference",)) == (
        GenericBoundInput("opaque-reference")
    )


def test_binding_traverses_nested_mappings() -> None:
    assert resolve(
        {"outer": {"inner": "opaque-reference"}},
        ("outer", "inner"),
    ) == GenericBoundInput("opaque-reference")


def test_binding_traverses_bounded_list_index() -> None:
    assert resolve(
        {"items": [{"reference": "first"}, {"reference": "second"}]},
        ("items", 1, "reference"),
    ) == GenericBoundInput("second")


@pytest.mark.parametrize(
    "path",
    [("missing",), ("items", 3, "reference")],
)
def test_binding_missing_key_or_invalid_index_fails_closed(
    path: tuple[str | int, ...],
) -> None:
    operation_input = GenericBoundInput(StepOutputBinding(1, path))

    with pytest.raises(StepOutputBindingError):
        resolve_step_output_bindings(
            operation_input,
            record=execution_record({"items": []}),
            consuming_step_index=2,
        )


@pytest.mark.parametrize("source_step_index", [2, 3])
def test_binding_rejects_self_or_future_step(source_step_index: int) -> None:
    with pytest.raises(StepOutputBindingError, match="earlier step"):
        resolve_step_output_bindings(
            GenericBoundInput(StepOutputBinding(source_step_index, ("reference",))),
            record=execution_record({"reference": "opaque"}),
            consuming_step_index=2,
        )


def test_binding_rejects_missing_source_step() -> None:
    record = execution_record({"reference": "opaque"})
    record = replace(
        record,
        total_steps=1,
        step_records=(record.step_records[1],),
    )

    with pytest.raises(StepOutputBindingError, match="does not exist"):
        resolve_step_output_bindings(
            GenericBoundInput(StepOutputBinding(1, ("reference",))),
            record=record,
            consuming_step_index=2,
        )


@pytest.mark.parametrize(
    ("status", "source_result"),
    [
        (StepExecutionStatus.PENDING, None),
        (StepExecutionStatus.FAILED, result({}, success=False)),
    ],
)
def test_binding_rejects_incomplete_or_failed_source_step(
    status: StepExecutionStatus,
    source_result: ToolExecutionResult | None,
) -> None:
    with pytest.raises(StepOutputBindingError, match="complete successfully"):
        resolve_step_output_bindings(
            GenericBoundInput(StepOutputBinding(1, ("reference",))),
            record=execution_record({}, source_status=status, source_result=source_result),
            consuming_step_index=2,
        )


def test_binding_rejects_wrong_resolved_scalar_type() -> None:
    with pytest.raises(StepOutputBindingError, match="wrong scalar type"):
        resolve_step_output_bindings(
            GenericBoundInput(StepOutputBinding(1, ("reference",))),
            record=execution_record({"reference": 123}),
            consuming_step_index=2,
        )


def test_resolved_value_passes_normal_typed_adapter_preflight() -> None:
    operation_input = EmailListMailboxesInput(
        StepOutputBinding(1, ("accounts", 0, "account_reference"))
    )
    resolved, resolutions = resolve_step_output_bindings(
        operation_input,
        record=execution_record({"accounts": [{"account_reference": "mailacct_0123456789abcdef"}]}),
        consuming_step_index=2,
    )
    adapter = EmailToolRuntimeAdapter(object())

    assert resolutions == (("account_reference", operation_input.account_reference),)
    assert adapter.preflight(ToolExecutionRequest("email", "list_mailboxes", asdict(resolved))) == {
        "account_reference": "mailacct_0123456789abcdef"
    }


class BindingBrokerClient:
    configured = True
    token = "t" * 44

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, object]]] = []

    def mail_accounts_list(self) -> dict:
        self.calls.append(("mail.accounts.list", {}))
        return {
            "outcome": "success",
            "result": {
                "results": [
                    {
                        "account_reference": "mailacct_0123456789abcdef",
                        "name": "Private account",
                        "email_addresses": ["private@example.com"],
                    }
                ],
                "result_count": 1,
                "truncated": False,
            },
        }

    def mail_mailboxes_list(self, account_reference: str) -> dict:
        self.calls.append(("mail.mailboxes.list", {"account_reference": account_reference}))
        return {
            "outcome": "success",
            "result": {
                "results": [
                    {
                        "mailbox_reference": "mailbox_0123456789abcdef",
                        "name": "Private mailbox",
                    }
                ],
                "result_count": 1,
                "truncated": False,
            },
        }


def test_runtime_resolution_preserves_snapshot_persists_binding_and_redacts_audit(
    tmp_path: Path,
) -> None:
    brain = tmp_path / "brain"
    brain.mkdir()
    database_path = tmp_path / "runtime" / "cauco.db"
    settings = Settings(brain_dir=brain, database_path=database_path)
    binding = StepOutputBinding(1, ("accounts", 0, "account_reference"))

    with TestClient(create_app(settings)) as client:
        pending = client.post(
            "/api/agents/plan-reviews",
            json={"instruction": "Inspect git status", "include_context": False},
        ).json()
        store = client.app.state.agent_plan_review_store
        stored = store._records[pending["review_id"]]
        plan = AgentPlan(
            agent_id=stored.plan.agent_id,
            agent_name=stored.plan.agent_name,
            status=stored.plan.status,
            objective="Exercise generic output binding.",
            context_used=stored.plan.context_used,
            steps=(
                AgentPlanStep(
                    1,
                    "List accounts",
                    "Produce bounded account metadata.",
                    (),
                    "List accounts.",
                    False,
                    False,
                    tool_reference=AgentToolReference("email", "list_accounts"),
                    operation_input=EmailListAccountsInput(),
                ),
                AgentPlanStep(
                    2,
                    "List mailboxes",
                    "Consume an explicitly approved prior-step output binding.",
                    (),
                    "List mailboxes for the bound account reference.",
                    False,
                    False,
                    tool_reference=AgentToolReference("email", "list_mailboxes"),
                    operation_input=EmailListMailboxesInput(binding),
                ),
            ),
            open_questions=(),
            warnings=stored.plan.warnings,
            requires_confirmation=False,
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

        approved_response = client.post(
            f"/api/agents/plan-reviews/{stored.review_id}/approve", json={}
        )
        assert approved_response.status_code == 200
        approved = approved_response.json()
        approved_plan = approved["plan"]
        approved_digest = approved["snapshot_digest"]
        assert approved_plan["steps"][1]["operation_input"] == {
            "account_reference": {
                "$step_output": {
                    "source_step_index": 1,
                    "path": ["accounts", 0, "account_reference"],
                    "value_type": "string",
                }
            }
        }

        adapter = client.app.state.tool_adapter_registry.get("email", "list_accounts")
        broker = BindingBrokerClient()
        adapter.broker_client = broker
        created = client.post("/api/executions", json={"review_id": stored.review_id}).json()
        run = client.post(f"/api/executions/{created['execution_id']}/run")

        assert run.status_code == 200
        assert run.json()["state"] == "completed"
        assert broker.calls == [
            ("mail.accounts.list", {}),
            (
                "mail.mailboxes.list",
                {"account_reference": "mailacct_0123456789abcdef"},
            ),
        ]

        refreshed = client.get(f"/api/agents/plan-reviews/{stored.review_id}").json()
        assert refreshed["plan"] == approved_plan
        assert refreshed["snapshot_digest"] == approved_digest

        execution = client.app.state.execution_store.get(created["execution_id"])
        events = [
            event
            for event in execution.audit_events
            if event.event_type == "input_binding_resolved"
        ]
        assert len(events) == 1
        assert dict(events[0].metadata) == {
            "consuming_step_index": 2,
            "source_step_index": 1,
            "destination_field": "account_reference",
            "path": "accounts/0/account_reference",
            "success": True,
        }
        assert "mailacct_0123456789abcdef" not in repr(dict(events[0].metadata))
        review_id = stored.review_id

    with TestClient(create_app(settings)) as restored_client:
        restored = restored_client.app.state.agent_plan_review_store.get(review_id)
        restored_input = restored.plan.steps[1].operation_input

        assert isinstance(restored_input, EmailListMailboxesInput)
        assert restored_input.account_reference == binding
        assert restored.snapshot_digest == approved_digest
