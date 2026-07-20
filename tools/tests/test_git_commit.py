import subprocess
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from cauco_tools import GitCommitInput, ToolExecutionRequest
from cauco_tools.adapters import GitCommitAdapter


def repository(tmp_path: Path) -> Path:
    root = tmp_path / "repository"
    root.mkdir()
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    subprocess.run(["git", "-C", str(root), "config", "user.name", "Test User"], check=True)
    subprocess.run(["git", "-C", str(root), "config", "user.email", "test@example.invalid"], check=True)
    (root / "base.txt").write_text("base\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(root), "add", "--", "base.txt"], check=True)
    subprocess.run(["git", "-C", str(root), "commit", "-qm", "Initial commit"], check=True)
    return root


def arguments(adapter: GitCommitAdapter) -> dict[str, object]:
    captured = adapter.inspect_commit("Add approved note", ("note.txt",))
    return {
        "message": captured["message"],
        "expected_staged_paths": captured["expected_staged_paths"],
        "staged_tree_id": captured["staged_tree_id"],
        "current_head_id": captured["current_head_id"],
        "current_branch": captured["current_branch"],
        "index_digest": captured["index_digest"],
    }


def test_git_commit_input_is_immutable_and_validates_message() -> None:
    value = GitCommitInput(" Add note ", ("note.txt",))
    assert value.message == "Add note"
    with pytest.raises(FrozenInstanceError):
        value.message = "Other"  # type: ignore[misc]
    for message in ("", "  ", "one\ntwo", "fixup! note", "-m unsafe", "x" * 121):
        with pytest.raises(ValueError):
            GitCommitInput(message, ("note.txt",))


def test_git_commit_uses_fixed_vector_and_verifies_exact_staged_tree(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = repository(tmp_path)
    (root / "note.txt").write_text("approved\n", encoding="utf-8")
    (root / "unstaged.txt").write_text("untouched\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(root), "add", "--", "note.txt"], check=True)
    adapter = GitCommitAdapter(root)
    request = ToolExecutionRequest("git", "commit", arguments(adapter))
    original = subprocess.run
    calls: list[tuple[list[str], dict[str, object]]] = []

    def spy(command: list[str], **kwargs: object):
        calls.append((command, kwargs))
        return original(command, **kwargs)

    monkeypatch.setattr(subprocess, "run", spy)
    result = adapter.execute(request)
    commit_call = next(item for item in calls if "commit" in item[0])
    assert commit_call[0][-4:] == ["commit", "--no-gpg-sign", "-m", "Add approved note"]
    assert commit_call[1]["shell"] is False
    assert result.mutation_performed is True
    assert result.structured_data["committed_paths"] == ("note.txt",)
    assert (root / "unstaged.txt").read_text(encoding="utf-8") == "untouched\n"


def test_git_commit_rejects_stale_index(tmp_path: Path) -> None:
    root = repository(tmp_path)
    (root / "note.txt").write_text("approved\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(root), "add", "--", "note.txt"], check=True)
    adapter = GitCommitAdapter(root)
    bound = arguments(adapter)
    (root / "other.txt").write_text("unexpected\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(root), "add", "--", "other.txt"], check=True)
    with pytest.raises(Exception, match="staged paths|Git state"):
        adapter.verify_commit_preview(bound)
