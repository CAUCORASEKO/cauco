import subprocess
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from cauco_tools import GitPushInput, ToolExecutionRequest
from cauco_tools.adapters import GitPushAdapter


def run(root: Path, *arguments: str) -> str:
    return subprocess.run(
        ["git", "-C", str(root), *arguments], check=True, capture_output=True, text=True
    ).stdout.strip()


def repository(tmp_path: Path) -> tuple[Path, Path]:
    remote = tmp_path / "remote.git"
    subprocess.run(["git", "init", "--bare", "-q", str(remote)], check=True)
    root = tmp_path / "repository"
    root.mkdir()
    run(root, "init", "-q")
    run(root, "config", "user.name", "Test User")
    run(root, "config", "user.email", "test@example.invalid")
    (root / "note.txt").write_text("base\n", encoding="utf-8")
    run(root, "add", "--", "note.txt")
    run(root, "commit", "-qm", "Initial commit")
    run(root, "remote", "add", "origin", str(remote))
    branch = run(root, "branch", "--show-current")
    run(root, "push", "-q", "origin", f"HEAD:refs/heads/{branch}")
    (root / "note.txt").write_text("published\n", encoding="utf-8")
    run(root, "add", "--", "note.txt")
    run(root, "commit", "-qm", "Publish approved note")
    return root, remote


def arguments(adapter: GitPushAdapter, root: Path) -> dict[str, object]:
    head = run(root, "rev-parse", "HEAD")
    branch = run(root, "branch", "--show-current")
    remote = adapter._remote_head("origin", branch)
    captured = adapter.inspect_push(GitPushInput("origin", branch, branch, head, remote))
    return {
        "remote": "origin", "local_branch": branch, "remote_branch": branch,
        "expected_local_commit": head, "expected_remote_commit": remote,
        "local_tree_id": captured["local_tree_id"], "outgoing_commits": captured["outgoing_commits"],
        "index_digest": captured["index_digest"], "remote_label": captured["remote_label"],
    }


def test_git_push_input_is_immutable_and_rejects_unsafe_values() -> None:
    value = GitPushInput("origin", "main", "main", "a" * 40, "b" * 40)
    with pytest.raises(FrozenInstanceError):
        value.remote = "other"  # type: ignore[misc]
    for remote, branch in (("", "main"), ("-origin", "main"), ("origin", "bad:ref")):
        with pytest.raises(ValueError):
            GitPushInput(remote, branch, branch, "a" * 40, "b" * 40)


def test_git_push_uses_fixed_refspec_and_updates_only_remote_branch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root, remote = repository(tmp_path)
    adapter = GitPushAdapter(root, allow_local_remotes=True)
    request = ToolExecutionRequest("git", "push", arguments(adapter, root))
    original = subprocess.run
    calls: list[tuple[list[str], dict[str, object]]] = []

    def spy(command: list[str], **kwargs: object):
        calls.append((command, kwargs))
        return original(command, **kwargs)

    monkeypatch.setattr(subprocess, "run", spy)
    result = adapter.execute(request)
    push_call = next(item for item in calls if "push" in item[0])
    branch = run(root, "branch", "--show-current")
    assert push_call[0][-4:] == ["push", "--porcelain", "origin", f"refs/heads/{branch}:refs/heads/{branch}"]
    assert push_call[1]["shell"] is False
    assert result.mutation_performed is True
    assert run(root, "rev-parse", "HEAD") == subprocess.run(
        ["git", "--git-dir", str(remote), "rev-parse", f"refs/heads/{branch}"],
        check=True, capture_output=True, text=True,
    ).stdout.strip()


def test_git_push_rejects_multiple_outgoing_commits(tmp_path: Path) -> None:
    root, _ = repository(tmp_path)
    (root / "extra.txt").write_text("extra\n", encoding="utf-8")
    run(root, "add", "--", "extra.txt")
    run(root, "commit", "-qm", "Second unpublished commit")
    adapter = GitPushAdapter(root, allow_local_remotes=True)
    with pytest.raises(Exception, match="exactly one"):
        arguments(adapter, root)
