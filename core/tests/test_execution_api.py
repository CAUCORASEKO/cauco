import subprocess
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import timedelta
from pathlib import Path

import pytest
from cauco_agents import AgentToolReference
from cauco_tools import ToolExecutionTimeoutError
from fastapi.testclient import TestClient

from cauco_core.agents.review_store import snapshot_digest
from cauco_core.config import Settings
from cauco_core.main import create_app


@pytest.fixture
def execution_client(tmp_path: Path) -> Iterator[TestClient]:
    brain = tmp_path / "brain"
    brain.mkdir()
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    subprocess.run(["git", "init", "-q", str(workspace)], check=True)
    (workspace / "README.md").write_text("# Cauco execution test\n", encoding="utf-8")
    (workspace / "zeta.txt").write_text("zeta", encoding="utf-8")
    with TestClient(create_app(Settings(brain_dir=brain, workspace_dir=workspace))) as client:
        yield client


def review(client: TestClient, instruction: str = "Inspect git status") -> dict[str, object]:
    created = client.post("/api/agents/plan-reviews", json={"instruction": instruction})
    assert created.status_code == 201
    approved = client.post(
        f"/api/agents/plan-reviews/{created.json()['review_id']}/approve", json={}
    )
    assert approved.status_code == 200
    return approved.json()


def execution(client: TestClient, approved: dict[str, object]) -> dict[str, object]:
    response = client.post("/api/executions", json={"review_id": approved["review_id"]})
    assert response.status_code == 201
    return response.json()


def test_create_requires_approved_unexpired_integrity_valid_review(
    execution_client: TestClient,
) -> None:
    pending = execution_client.post(
        "/api/agents/plan-reviews", json={"instruction": "Inspect git status"}
    ).json()
    assert execution_client.post(
        "/api/executions", json={"review_id": pending["review_id"]}
    ).status_code == 409

    approved = review(execution_client)
    store = execution_client.app.state.agent_plan_review_store
    stored = store._records[approved["review_id"]]
    changed = replace(stored.plan.steps[0], description="tampered")
    store._records[approved["review_id"]] = replace(
        stored, plan=replace(stored.plan, steps=(changed, *stored.plan.steps[1:]))
    )
    assert execution_client.post(
        "/api/executions", json={"review_id": approved["review_id"]}
    ).status_code == 409


@pytest.mark.parametrize("decision", ["reject", "cancel"])
def test_rejected_and_cancelled_reviews_cannot_create_execution(
    execution_client: TestClient, decision: str
) -> None:
    pending = execution_client.post(
        "/api/agents/plan-reviews", json={"instruction": "Inspect git status"}
    ).json()
    body = {"reason": "not approved"} if decision == "reject" else {}
    execution_client.post(
        f"/api/agents/plan-reviews/{pending['review_id']}/{decision}", json=body
    )
    response = execution_client.post(
        "/api/executions", json={"review_id": pending["review_id"]}
    )
    assert response.status_code == 409


def test_expired_approval_cannot_create_execution(execution_client: TestClient) -> None:
    approved = review(execution_client)
    expires = execution_client.app.state.agent_plan_review_store.get(
        approved["review_id"]
    ).expires_at
    execution_client.app.state.execution_service.clock = lambda: expires + timedelta(seconds=1)
    response = execution_client.post(
        "/api/executions", json={"review_id": approved["review_id"]}
    )
    assert response.status_code == 409


def test_record_creation_is_inert_then_git_status_executes_once(
    execution_client: TestClient,
) -> None:
    approved = review(execution_client)
    before = execution_client.get(
        f"/api/agents/plan-reviews/{approved['review_id']}"
    ).json()
    created = execution(execution_client, approved)
    duplicate_creation = execution_client.post(
        "/api/executions", json={"review_id": approved["review_id"]}
    )
    git_step = next(
        item
        for item in created["step_records"]
        if item["tool_id"] == "git" and item["operation_id"] == "status"
    )

    assert created["status"] == "pending_execution"
    assert duplicate_creation.status_code == 409
    assert created["execution_performed"] is False
    assert all(not item["execution_performed"] for item in created["step_records"])
    response = execution_client.post(
        f"/api/executions/{created['execution_id']}/steps/{git_step['step_index']}/execute",
        json={"max_output_chars": 100},
    )
    repeated = execution_client.post(
        f"/api/executions/{created['execution_id']}/steps/{git_step['step_index']}/execute",
        json={},
    )
    after = execution_client.get(
        f"/api/agents/plan-reviews/{approved['review_id']}"
    ).json()

    assert response.status_code == 200
    executed = next(
        item for item in response.json()["step_records"]
        if item["step_index"] == git_step["step_index"]
    )
    assert executed["execution_performed"] is True
    assert executed["result"]["success"] is True
    assert len(executed["result"]["output"]) <= 100
    assert repeated.status_code == 409
    assert before["snapshot_digest"] == after["snapshot_digest"]
    assert before["plan"] == after["plan"]
    assert after["execution_performed"] is False
    assert str(execution_client.app.state.workspace_policy.root) not in response.text
    assert any(event["event_type"] == "step_completed" for event in response.json()["audit_events"])


def test_filesystem_list_and_read_are_real_bounded_operations(
    execution_client: TestClient,
) -> None:
    approved = review(execution_client, "Review README.md in the git repository")
    created = execution(execution_client, approved)
    list_step = next(
        item for item in created["step_records"]
        if item["operation_id"] == "list_directory"
    )
    read_step = next(
        item for item in created["step_records"]
        if item["operation_id"] == "read_file"
    )

    listed = execution_client.post(
        f"/api/executions/{created['execution_id']}/steps/{list_step['step_index']}/execute",
        json={"max_entries": 1},
    )
    read = execution_client.post(
        f"/api/executions/{created['execution_id']}/steps/{read_step['step_index']}/execute",
        json={"max_chars": 7},
    )

    listed_step = next(
        item for item in listed.json()["step_records"]
        if item["step_index"] == list_step["step_index"]
    )
    read_record = next(
        item for item in read.json()["step_records"]
        if item["step_index"] == read_step["step_index"]
    )
    assert listed_step["result"]["truncated"] is True
    assert len(listed_step["result"]["structured_data"]["entries"]) == 1
    assert read_record["result"]["output"] == "# Cauco"
    assert read_record["result"]["structured_data"]["path"] == "README.md"


def test_client_cannot_replace_tool_operation_or_target(execution_client: TestClient) -> None:
    created = execution(execution_client, review(execution_client))
    response = execution_client.post(
        f"/api/executions/{created['execution_id']}/steps/2/execute",
        json={"tool_id": "git", "operation_id": "commit", "target": "/etc/passwd"},
    )
    assert response.status_code == 422
    assert execution_client.get(f"/api/executions/{created['execution_id']}").json()[
        "execution_performed"
    ] is False


def test_sensitive_approved_target_is_denied_without_invocation(
    execution_client: TestClient,
) -> None:
    approved = review(execution_client, "Review README.md in the git repository")
    store = execution_client.app.state.agent_plan_review_store
    stored = store._records[approved["review_id"]]
    step = stored.plan.steps[2]
    changed = replace(
        step, tool_reference=AgentToolReference("filesystem", "read_file", ".env")
    )
    plan = replace(stored.plan, steps=(*stored.plan.steps[:2], changed, *stored.plan.steps[3:]))
    digest = snapshot_digest(
        instruction=stored.instruction,
        selected_agent_id=stored.selected_agent_id,
        routing=stored.routing,
        context=stored.context,
        plan=plan,
    )
    store._records[stored.review_id] = replace(stored, plan=plan, snapshot_digest=digest)
    created = execution(
        execution_client,
        execution_client.get(f"/api/agents/plan-reviews/{stored.review_id}").json(),
    )
    response = execution_client.post(
        f"/api/executions/{created['execution_id']}/steps/3/execute", json={}
    )
    current = execution_client.get(f"/api/executions/{created['execution_id']}").json()
    assert response.status_code == 403
    assert current["execution_performed"] is False
    assert any(event["event_type"] == "operation_denied" for event in current["audit_events"])
    assert ".env" not in " ".join(event["safe_message"] for event in current["audit_events"])


def test_timeout_is_stored_as_failed_performed_step(
    execution_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    created = execution(execution_client, review(execution_client))
    adapter = execution_client.app.state.tool_adapter_registry.get("git", "status")

    def timeout(request: object):
        raise ToolExecutionTimeoutError()

    monkeypatch.setattr(adapter, "execute", timeout)
    response = execution_client.post(
        f"/api/executions/{created['execution_id']}/steps/2/execute", json={}
    )
    step = next(item for item in response.json()["step_records"] if item["step_index"] == 2)
    assert response.status_code == 200
    assert response.json()["status"] == "failed"
    assert response.json()["execution_performed"] is True
    assert step["execution_performed"] is True
    assert any(event["event_type"] == "timeout" for event in response.json()["audit_events"])


def test_unsupported_step_is_blocked_and_audited(execution_client: TestClient) -> None:
    created = execution(execution_client, review(execution_client, "Review the git diff"))
    skipped = next(item for item in created["step_records"] if item["operation_id"] == "diff")
    response = execution_client.post(
        f"/api/executions/{created['execution_id']}/steps/{skipped['step_index']}/execute",
        json={},
    )
    stored = execution_client.get(f"/api/executions/{created['execution_id']}").json()
    assert response.status_code == 409
    assert stored["execution_performed"] is False
    assert any(event["event_type"] == "operation_denied" for event in stored["audit_events"])


def test_pending_execution_can_cancel_and_list_filters_work(execution_client: TestClient) -> None:
    created = execution(execution_client, review(execution_client))
    cancelled = execution_client.post(f"/api/executions/{created['execution_id']}/cancel")
    repeated = execution_client.post(f"/api/executions/{created['execution_id']}/cancel")
    listed = execution_client.get(
        "/api/executions", params={"status": "cancelled", "review_id": created["review_id"]}
    )
    assert cancelled.json()["status"] == "cancelled"
    assert repeated.status_code == 409
    assert listed.json()["count"] == 1


def test_execution_completes_after_all_eligible_steps_finish(
    execution_client: TestClient,
) -> None:
    created = execution(execution_client, review(execution_client))
    current = created
    for step in created["step_records"]:
        if step["status"] != "pending":
            continue
        response = execution_client.post(
            f"/api/executions/{created['execution_id']}/steps/{step['step_index']}/execute",
            json={},
        )
        assert response.status_code == 200
        current = response.json()
    assert current["status"] == "completed"
    assert current["execution_performed"] is True
    assert any(
        event["event_type"] == "execution_completed"
        for event in current["audit_events"]
    )


def test_concurrent_same_step_allows_one_invocation(execution_client: TestClient) -> None:
    created = execution(execution_client, review(execution_client))
    git_step = next(
        item for item in created["step_records"]
        if item["tool_id"] == "git" and item["operation_id"] == "status"
    )
    path = f"/api/executions/{created['execution_id']}/steps/{git_step['step_index']}/execute"

    def run() -> int:
        return execution_client.post(path, json={}).status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        statuses = list(pool.map(lambda _: run(), range(2)))
    assert sorted(statuses) == [200, 409]


def test_unknown_execution_and_step_return_not_found(execution_client: TestClient) -> None:
    assert execution_client.get("/api/executions/exec_unknown").status_code == 404
    created = execution(execution_client, review(execution_client))
    response = execution_client.post(
        f"/api/executions/{created['execution_id']}/steps/999/execute", json={}
    )
    assert response.status_code == 404
