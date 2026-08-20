import subprocess
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Event, Lock

import pytest
from cauco_tools import ToolExecutionTimeoutError
from fastapi.testclient import TestClient

from cauco_core.agents.review_store import PlanReviewIntegrityError
from cauco_core.config import Settings
from cauco_core.execution.recovery import RecoveryContext, RecoveryDecision, RecoveryPolicy
from cauco_core.main import create_app
from cauco_core.mutations.models import MutationCapacityError, MutationConflictError


@pytest.fixture
def runtime_client(tmp_path: Path) -> Iterator[TestClient]:
    brain = tmp_path / "brain"
    brain.mkdir()
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    subprocess.run(["git", "init", "-q", str(workspace)], check=True)
    (workspace / "README.md").write_text("# runtime\n", encoding="utf-8")
    with TestClient(create_app(Settings(brain_dir=brain, workspace_dir=workspace))) as client:
        yield client


def approved_execution(client: TestClient, instruction: str) -> tuple[dict, dict]:
    review = client.post("/api/agents/plan-reviews", json={"instruction": instruction})
    approved = client.post(
        f"/api/agents/plan-reviews/{review.json()['review_id']}/approve", json={}
    )
    execution = client.post(
        "/api/executions", json={"review_id": approved.json()["review_id"]}
    )
    assert review.status_code == 201
    assert approved.status_code == 200
    assert execution.status_code == 201
    return approved.json(), execution.json()


def test_runtime_advances_read_only_steps_in_order_and_skips_disabled_steps(
    runtime_client: TestClient,
) -> None:
    _, execution = approved_execution(runtime_client, "Review README.md in the git repository")

    response = runtime_client.post(f"/api/executions/{execution['execution_id']}/run")
    record = runtime_client.get(f"/api/executions/{execution['execution_id']}").json()

    assert response.status_code == 200
    assert response.json()["state"] == "completed"
    started = [
        event["step_index"]
        for event in record["audit_events"]
        if event["event_type"] == "step_started"
    ]
    assert started == sorted(started)
    assert all(step["status"] in {"completed", "skipped"} for step in record["step_records"])


def test_mutation_pauses_for_confirmation_then_resume_continues(
    runtime_client: TestClient,
) -> None:
    approved, execution = approved_execution(
        runtime_client, "In git repository create workspace file notes.txt containing hello"
    )
    before_plan = approved["plan"]
    before_digest = approved["snapshot_digest"]

    paused = runtime_client.post(f"/api/executions/{execution['execution_id']}/run")
    assert paused.json()["state"] == "awaiting_confirmation"
    assert paused.json()["preview_id"].startswith("mutprev_")
    assert not (runtime_client.app.state.workspace_policy.root / "notes.txt").exists()

    step = next(
        item for item in execution["step_records"] if item["operation_id"] == "write_text_file"
    )
    preview = runtime_client.get(
        f"/api/executions/{execution['execution_id']}/steps/{step['step_index']}/mutation-preview"
    ).json()
    confirmed = runtime_client.post(
        f"/api/executions/{execution['execution_id']}/steps/{step['step_index']}/confirm-mutation",
        json={
            "preview_id": preview["preview_id"],
            "preview_digest": preview["preview_digest"],
            "confirmation_phrase": preview["confirmation_phrase"],
        },
    )
    resumed = runtime_client.post(f"/api/executions/{execution['execution_id']}/resume")
    review = runtime_client.get(f"/api/agents/plan-reviews/{approved['review_id']}").json()

    assert confirmed.status_code == 200
    assert resumed.json()["state"] == "completed"
    assert (runtime_client.app.state.workspace_policy.root / "notes.txt").read_text() == "hello"
    assert review["plan"] == before_plan
    assert review["snapshot_digest"] == before_digest


def test_concurrent_run_does_not_execute_a_step_twice(
    runtime_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, execution = approved_execution(runtime_client, "Inspect git status")
    adapter = runtime_client.app.state.tool_adapter_registry.get("git", "status")
    original = adapter.execute
    calls = 0
    guard = Lock()

    def counted(request):
        nonlocal calls
        with guard:
            calls += 1
        return original(request)

    monkeypatch.setattr(adapter, "execute", counted)
    expected_calls = sum(
        step["tool_id"] == "git"
        and step["operation_id"] == "status"
        and step["status"] == "pending"
        for step in execution["step_records"]
    )
    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(
            pool.map(
                lambda _: runtime_client.app.state.task_runtime.run(execution["execution_id"]),
                range(2),
            )
        )

    assert all(outcome.state.value == "completed" for outcome in outcomes)
    assert calls == expected_calls
    record = runtime_client.app.state.execution_store.get(execution["execution_id"])
    starts = [
        event.step_index for event in record.audit_events if event.event_type == "step_started"
    ]
    assert len(starts) == len(set(starts))


def test_runtime_retries_one_allowlisted_transient_read_failure(
    runtime_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, execution = approved_execution(runtime_client, "Inspect git status")
    adapter = runtime_client.app.state.tool_adapter_registry.get("git", "status")
    original = adapter.execute
    calls = 0

    def transient(request):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise ToolExecutionTimeoutError()
        return original(request)

    monkeypatch.setattr(adapter, "execute", transient)
    expected_calls = 1 + sum(
        step["tool_id"] == "git"
        and step["operation_id"] == "status"
        and step["status"] == "pending"
        for step in execution["step_records"]
    )
    outcome = runtime_client.app.state.task_runtime.run(execution["execution_id"])
    record = runtime_client.app.state.execution_store.get(execution["execution_id"])

    assert outcome.state.value == "completed"
    assert calls == expected_calls
    assert sum(event.event_type == "recovery_retry" for event in record.audit_events) == 1


@pytest.mark.parametrize(
    ("context", "decision"),
    [
        (
            RecoveryContext("git", "status", "forbidden", False, False, 1),
            RecoveryDecision.ABORT,
        ),
        (
            RecoveryContext("git", "status", "snapshot_mismatch", False, False, 1),
            RecoveryDecision.ABORT,
        ),
        (
            RecoveryContext("git", "commit", "timeout", True, False, 1),
            RecoveryDecision.ABORT,
        ),
        (
            RecoveryContext("filesystem", "write_text_file", "timeout", True, True, 1),
            RecoveryDecision.ABORT,
        ),
        (
            RecoveryContext("git", "status", "timeout", True, False, 2),
            RecoveryDecision.ABORT,
        ),
    ],
)
def test_recovery_policy_is_bounded_and_fail_closed(
    context: RecoveryContext, decision: RecoveryDecision
) -> None:
    assert RecoveryPolicy().evaluate(context) is decision


def test_recovery_policy_never_automatically_skips_without_optionality() -> None:
    policy = RecoveryPolicy()
    contexts = (
        RecoveryContext("git", "status", "target_missing", False, False, 1),
        RecoveryContext("filesystem", "read_file", "not_found", False, False, 1),
        RecoveryContext("git", "status", "timeout", True, False, 2),
    )

    assert all(policy.evaluate(context) is not RecoveryDecision.SKIP for context in contexts)


def test_integrity_failure_aborts_and_preserves_approved_plan_and_snapshot(
    runtime_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    approved, execution = approved_execution(runtime_client, "Inspect git status")

    def integrity_failure(*args, **kwargs):
        raise PlanReviewIntegrityError("integrity failed")

    monkeypatch.setattr(
        runtime_client.app.state.execution_service, "execute_step", integrity_failure
    )
    outcome = runtime_client.app.state.task_runtime.run(execution["execution_id"])
    unchanged = runtime_client.get(
        f"/api/agents/plan-reviews/{approved['review_id']}"
    ).json()

    assert outcome.state.value == "failed"
    assert outcome.recovery_decision is RecoveryDecision.ABORT
    assert unchanged["plan"] == approved["plan"]
    assert unchanged["snapshot_digest"] == approved["snapshot_digest"]


def test_stale_operational_state_requires_replan(
    runtime_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    approved, execution = approved_execution(
        runtime_client, "In git repository create workspace file notes.txt containing hello"
    )

    def stale(*args, **kwargs):
        raise MutationConflictError("The create-only target already exists.")

    monkeypatch.setattr(runtime_client.app.state.mutation_service, "create_preview", stale)
    outcome = runtime_client.app.state.task_runtime.run(execution["execution_id"])
    unchanged = runtime_client.get(
        f"/api/agents/plan-reviews/{approved['review_id']}"
    ).json()

    assert outcome.state.value == "replan_required"
    assert outcome.recovery_decision is RecoveryDecision.REPLAN_REQUIRED
    assert unchanged["plan"] == approved["plan"]
    assert unchanged["snapshot_digest"] == approved["snapshot_digest"]


def test_mutation_preview_capacity_failure_aborts_safely(
    runtime_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, execution = approved_execution(
        runtime_client, "In git repository create workspace file notes.txt containing hello"
    )

    def full(*args, **kwargs):
        raise MutationCapacityError("Mutation preview capacity is full.")

    monkeypatch.setattr(runtime_client.app.state.mutation_service, "create_preview", full)
    response = runtime_client.post(f"/api/executions/{execution['execution_id']}/run")

    assert response.status_code == 200
    assert response.json()["state"] == "failed"
    assert response.json()["recovery_decision"] == "abort"


def test_repeated_observation_of_same_preview_does_not_duplicate_awaiting_event(
    runtime_client: TestClient,
) -> None:
    _, execution = approved_execution(
        runtime_client, "In git repository create workspace file notes.txt containing hello"
    )
    runtime = runtime_client.app.state.task_runtime

    first = runtime.run(execution["execution_id"])
    second = runtime.run(execution["execution_id"])
    third = runtime.resume(execution["execution_id"])
    record = runtime_client.app.state.execution_store.get(execution["execution_id"])

    assert first.preview_id == second.preview_id == third.preview_id
    assert sum(
        event.event_type == "awaiting_confirmation" for event in record.audit_events
    ) == 1


def test_cancel_awaiting_unconfirmed_mutation_at_safe_boundary(
    runtime_client: TestClient,
) -> None:
    _, execution = approved_execution(
        runtime_client, "In git repository create workspace file notes.txt containing hello"
    )
    paused = runtime_client.app.state.task_runtime.run(execution["execution_id"])
    before = runtime_client.app.state.execution_store.get(execution["execution_id"])

    response = runtime_client.post(f"/api/executions/{execution['execution_id']}/cancel")
    after = runtime_client.app.state.execution_store.get(execution["execution_id"])
    preview = runtime_client.app.state.mutation_preview_store.get(paused.preview_id)

    assert any(step.status.value == "completed" for step in before.step_records)
    assert paused.state.value == "awaiting_confirmation"
    assert response.status_code == 200
    assert response.json()["status"] == "cancelled"
    assert preview.status.value == "cancelled"
    assert all(step.status.value != "running" for step in after.step_records)
    assert not (runtime_client.app.state.workspace_policy.root / "notes.txt").exists()


def test_cancellation_waits_for_running_adapter_without_interrupting_it(
    runtime_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, execution = approved_execution(
        runtime_client, "In git repository create workspace file notes.txt containing hello"
    )
    adapter = runtime_client.app.state.tool_adapter_registry.get(
        "filesystem", "list_directory"
    )
    original = adapter.execute
    entered = Event()
    release = Event()

    def blocked(request):
        entered.set()
        assert release.wait(timeout=5)
        return original(request)

    monkeypatch.setattr(adapter, "execute", blocked)
    runtime = runtime_client.app.state.task_runtime
    with ThreadPoolExecutor(max_workers=2) as pool:
        advancing = pool.submit(runtime.run, execution["execution_id"])
        assert entered.wait(timeout=5)
        cancelling = pool.submit(runtime.cancel, execution["execution_id"])
        assert not cancelling.done()
        running = runtime_client.app.state.execution_store.get(execution["execution_id"])
        assert any(step.status.value == "running" for step in running.step_records)
        release.set()
        assert advancing.result(timeout=5).state.value == "awaiting_confirmation"
        assert cancelling.result(timeout=5).state.value == "cancelled"


def test_runtime_cancellation_and_unknown_execution_are_safe(runtime_client: TestClient) -> None:
    _, execution = approved_execution(runtime_client, "Inspect git status")
    cancelled = runtime_client.post(f"/api/executions/{execution['execution_id']}/cancel")
    runtime = runtime_client.get(f"/api/executions/{execution['execution_id']}/runtime")
    unknown = runtime_client.post("/api/executions/exec_missing_runtime_identifier/run")

    assert cancelled.status_code == 200
    assert runtime.json()["state"] == "cancelled"
    assert unknown.status_code == 404
