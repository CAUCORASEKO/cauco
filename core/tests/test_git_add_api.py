import subprocess

from fastapi.testclient import TestClient
from test_mutation_api import approved_execution, confirm, mutation_step, preview

pytest_plugins = ("test_mutation_api",)


def test_git_add_preview_is_inert_then_stages_exact_approved_file(
    mutation_client: TestClient,
) -> None:
    workspace = mutation_client.app.state.workspace_policy.root
    (workspace / "approved.txt").write_text("approved\n", encoding="utf-8")
    (workspace / "unapproved.txt").write_text("unapproved\n", encoding="utf-8")
    _, execution = approved_execution(mutation_client, "git add approved.txt")
    step = mutation_step(execution, "add")

    created = preview(mutation_client, execution, step)
    assert created.status_code == 201, created.text
    data = created.json()
    assert data["confirmation_phrase"] == "STAGE APPROVED FILES"
    assert data["normalized_arguments"]["paths"] == ["approved.txt"]
    assert str(workspace) not in created.text
    assert (
        subprocess.run(
            ["git", "-C", str(workspace), "diff", "--cached", "--quiet"], check=False
        ).returncode
        == 0
    )

    wrong = confirm(mutation_client, execution, step, data, "CONFIRM")
    assert wrong.status_code == 422
    completed = confirm(mutation_client, execution, step, data, "STAGE APPROVED FILES")
    assert completed.status_code == 200, completed.text
    record = completed.json()
    result = next(
        item for item in record["step_records"] if item["step_index"] == step["step_index"]
    )["result"]
    assert result["mutation_performed"] is True
    assert result["structured_data"]["staged_paths"] == ["approved.txt"]
    staged = subprocess.run(
        ["git", "-C", str(workspace), "diff", "--cached", "--name-only"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.splitlines()
    assert staged == ["approved.txt"]


def test_git_add_stale_worktree_is_rejected_without_staging(mutation_client: TestClient) -> None:
    workspace = mutation_client.app.state.workspace_policy.root
    target = workspace / "approved.txt"
    target.write_text("before\n", encoding="utf-8")
    _, execution = approved_execution(mutation_client, "git add approved.txt")
    step = mutation_step(execution, "add")
    data = preview(mutation_client, execution, step).json()
    target.write_text("after\n", encoding="utf-8")

    stale = confirm(mutation_client, execution, step, data, "STAGE APPROVED FILES")
    assert stale.status_code == 409
    current = mutation_client.get(f"/api/executions/{execution['execution_id']}").json()
    assert current["execution_performed"] is False
    assert (
        subprocess.run(
            ["git", "-C", str(workspace), "diff", "--cached", "--quiet"], check=False
        ).returncode
        == 0
    )
