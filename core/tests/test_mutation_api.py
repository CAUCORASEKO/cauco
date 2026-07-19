import shutil
import subprocess
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from cauco_tools import ToolExecutionError
from fastapi.testclient import TestClient

from cauco_core.config import Settings
from cauco_core.main import create_app
from cauco_core.memory_writing.store import ProposalNotFoundError


@pytest.fixture
def mutation_client(tmp_path: Path) -> Iterator[TestClient]:
    source = Path(__file__).resolve().parents[2] / "brain-template"
    brain = tmp_path / "brain"
    shutil.copytree(source, brain)
    (brain / "tasks.md").unlink()
    (brain / "Tasks.md").write_text(
        "# Tasks\n\n## Today\n\n## This Week\n\n## Backlog\n",
        encoding="utf-8",
    )
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    subprocess.run(["git", "init", "-q", str(workspace)], check=True)
    with TestClient(create_app(Settings(brain_dir=brain, workspace_dir=workspace))) as client:
        yield client


def approved_execution(client: TestClient, instruction: str) -> tuple[dict, dict]:
    review = client.post("/api/agents/plan-reviews", json={"instruction": instruction})
    assert review.status_code == 201, review.text
    approved = client.post(
        f"/api/agents/plan-reviews/{review.json()['review_id']}/approve", json={}
    )
    assert approved.status_code == 200, approved.text
    execution = client.post("/api/executions", json={"review_id": approved.json()["review_id"]})
    assert execution.status_code == 201, execution.text
    return approved.json(), execution.json()


def mutation_step(execution: dict, operation: str) -> dict:
    return next(item for item in execution["step_records"] if item["operation_id"] == operation)


def preview(client: TestClient, execution: dict, step: dict):
    return client.post(
        f"/api/executions/{execution['execution_id']}/steps/{step['step_index']}/mutation-preview",
        json={},
    )


def confirm(client: TestClient, execution: dict, step: dict, mutation_preview: dict, phrase: str):
    return client.post(
        f"/api/executions/{execution['execution_id']}/steps/{step['step_index']}/confirm-mutation",
        json={
            "preview_id": mutation_preview["preview_id"],
            "preview_digest": mutation_preview["preview_digest"],
            "confirmation_phrase": phrase,
        },
    )


def test_filesystem_preview_is_inert_and_exact_confirmation_creates_file(
    mutation_client: TestClient,
) -> None:
    instruction = "In git repository create workspace file notes.txt containing hello phase seven"
    approved, execution = approved_execution(mutation_client, instruction)
    step = mutation_step(execution, "write_text_file")
    workspace = mutation_client.app.state.workspace_policy.root
    original_plan = approved["plan"]
    original_digest = approved["snapshot_digest"]

    read_only = mutation_client.post(
        f"/api/executions/{execution['execution_id']}/steps/{step['step_index']}/execute", json={}
    )
    created_preview = preview(mutation_client, execution, step)
    data = created_preview.json()

    assert read_only.status_code == 409
    assert created_preview.status_code == 201
    assert data["preview_id"].startswith("mutprev_") and len(data["preview_id"]) > 20
    assert data["target"] == "notes.txt"
    assert not (workspace / "notes.txt").exists()
    current = mutation_client.get(f"/api/executions/{execution['execution_id']}").json()
    assert current["execution_performed"] is False

    wrong = confirm(mutation_client, execution, step, data, "yes")
    mismatch = dict(data)
    mismatch["preview_digest"] = "0" * 64
    wrong_digest = confirm(mutation_client, execution, step, mismatch, data["confirmation_phrase"])
    assert wrong.status_code == 422
    assert wrong_digest.status_code == 409
    assert not (workspace / "notes.txt").exists()

    result = confirm(mutation_client, execution, step, data, data["confirmation_phrase"])
    repeated = confirm(mutation_client, execution, step, data, data["confirmation_phrase"])
    record = mutation_step(result.json(), "write_text_file")
    refreshed = mutation_client.get(f"/api/agents/plan-reviews/{approved['review_id']}").json()

    assert result.status_code == 200
    assert repeated.status_code == 409
    assert (workspace / "notes.txt").read_text(encoding="utf-8") == "hello phase seven"
    assert record["execution_performed"] is True
    assert record["result"]["mutation_performed"] is True
    assert record["result"]["structured_data"]["verification_passed"] is True
    assert record["result"]["structured_data"]["relative_path"] == "notes.txt"
    assert str(workspace) not in result.text
    assert refreshed["plan"] == original_plan
    assert refreshed["snapshot_digest"] == original_digest
    assert "hello phase seven" not in " ".join(
        item["safe_message"] for item in result.json()["audit_events"]
    )


def test_filesystem_replace_detects_stale_state_and_creates_internal_backup(
    mutation_client: TestClient,
) -> None:
    workspace = mutation_client.app.state.workspace_policy.root
    target = workspace / "notes.md"
    target.write_text("old\n", encoding="utf-8")
    _, execution = approved_execution(
        mutation_client, "In git repository replace workspace file notes.md with new text"
    )
    step = mutation_step(execution, "write_text_file")
    first = preview(mutation_client, execution, step).json()
    target.write_text("external\n", encoding="utf-8")
    stale = confirm(mutation_client, execution, step, first, first["confirmation_phrase"])
    assert stale.status_code == 409
    assert target.read_text(encoding="utf-8") == "external\n"

    second = preview(mutation_client, execution, step).json()
    result = confirm(mutation_client, execution, step, second, second["confirmation_phrase"])
    structured = mutation_step(result.json(), "write_text_file")["result"]["structured_data"]
    assert result.status_code == 200
    assert target.read_text(encoding="utf-8") == "new text"
    assert structured["backup_created"] is True
    assert any((workspace / ".cauco-backups").iterdir())
    assert str(workspace) not in result.text


def test_failed_controlled_backup_prevents_replacement(
    mutation_client: TestClient, tmp_path: Path
) -> None:
    workspace = mutation_client.app.state.workspace_policy.root
    target = workspace / "protected.txt"
    target.write_text("original", encoding="utf-8")
    _, execution = approved_execution(
        mutation_client,
        "In git repository replace workspace file protected.txt with replacement",
    )
    step = mutation_step(execution, "write_text_file")
    created = preview(mutation_client, execution, step).json()
    outside = tmp_path / "outside-backups"
    outside.mkdir()
    (workspace / ".cauco-backups").symlink_to(outside, target_is_directory=True)

    response = confirm(
        mutation_client, execution, step, created, created["confirmation_phrase"]
    )
    record = mutation_step(response.json(), "write_text_file")
    assert response.status_code == 200
    assert record["result"]["success"] is False
    assert record["result"]["error_code"] == "backup_failed"
    assert target.read_text(encoding="utf-8") == "original"
    assert not any(outside.iterdir())


def test_memory_create_proposal_never_writes_markdown_before_or_after_execution(
    mutation_client: TestClient,
) -> None:
    brain = mutation_client.app.state.memory_service.brain_dir
    before = {path.name: path.read_bytes() for path in brain.glob("*.md")}
    _, execution = approved_execution(mutation_client, "Add task validate controlled mutation")
    step = mutation_step(execution, "create_proposal")
    created = preview(mutation_client, execution, step)
    proposal_id = created.json()["proposed_after_state"]["proposal_id"]
    assert created.status_code == 201
    assert {path.name: path.read_bytes() for path in brain.glob("*.md")} == before
    with pytest.raises(ProposalNotFoundError):
        mutation_client.app.state.memory_write_proposal_store.get(proposal_id)

    result = confirm(
        mutation_client, execution, step, created.json(), created.json()["confirmation_phrase"]
    )
    stored = mutation_client.app.state.memory_write_proposal_store.get(proposal_id)
    assert result.status_code == 200
    assert stored.state.value == "pending"
    assert {path.name: path.read_bytes() for path in brain.glob("*.md")} == before


def test_memory_confirmation_applies_exact_proposal_with_backup_and_refresh(
    mutation_client: TestClient,
) -> None:
    proposal = mutation_client.post(
        "/api/memory/write-proposals",
        json={"instruction": "Add task verify memory confirmation"},
    ).json()
    _, execution = approved_execution(
        mutation_client, f"Confirm task proposal {proposal['proposal_id']}"
    )
    step = mutation_step(execution, "confirm_proposal")
    tasks = mutation_client.app.state.memory_service.brain_dir / "Tasks.md"
    assert any(
        item.relative_path.casefold() == "tasks.md"
        for item in mutation_client.app.state.memory_engine.list_objects()
    ), [item.relative_path for item in mutation_client.app.state.memory_engine.list_objects()]
    before = tasks.read_bytes()
    created = preview(mutation_client, execution, step)
    assert created.status_code == 201
    assert tasks.read_bytes() == before

    result = confirm(
        mutation_client, execution, step, created.json(), created.json()["confirmation_phrase"]
    )
    record = mutation_step(result.json(), "confirm_proposal")
    assert result.status_code == 200
    assert record["result"]["success"], record
    assert tasks.read_bytes() != before
    assert tasks.with_name("Tasks.md.bak").read_bytes() == before
    assert record["result"]["structured_data"]["memory_refreshed"] is True
    assert record["result"]["structured_data"]["verification_passed"] is True
    assert (
        mutation_client.app.state.memory_write_proposal_store.get(
            proposal["proposal_id"]
        ).state.value
        == "applied"
    )


def test_confirmation_contract_forbids_argument_replacement_and_concurrency_is_single_use(
    mutation_client: TestClient,
) -> None:
    _, execution = approved_execution(
        mutation_client, "In git repository create workspace file once.txt containing exactly once"
    )
    step = mutation_step(execution, "write_text_file")
    data = preview(mutation_client, execution, step).json()
    path = (
        f"/api/executions/{execution['execution_id']}/steps/{step['step_index']}/confirm-mutation"
    )
    replaced = mutation_client.post(
        path,
        json={
            "preview_id": data["preview_id"],
            "preview_digest": data["preview_digest"],
            "confirmation_phrase": data["confirmation_phrase"],
            "content": "replacement",
            "target": ".env",
            "operation_id": "delete_file",
        },
    )
    assert replaced.status_code == 422

    def run() -> int:
        return confirm(
            mutation_client, execution, step, data, data["confirmation_phrase"]
        ).status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        statuses = list(pool.map(lambda _: run(), range(2)))
    assert sorted(statuses) == [200, 409]


@pytest.mark.parametrize(
    "target",
    [".env", "../escape.txt", ".git/config", "script.py", "package.json", "id_rsa.txt"],
)
def test_forbidden_filesystem_targets_are_rejected_without_mutation(
    mutation_client: TestClient, target: str
) -> None:
    adapter = mutation_client.app.state.tool_adapter_registry.get("filesystem", "write_text_file")
    with pytest.raises(ToolExecutionError):
        adapter.resolve_target(target)
