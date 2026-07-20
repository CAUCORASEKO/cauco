import subprocess
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from cauco_tools import GitAddInput, ToolExecutionError, ToolExecutionRequest
from cauco_tools.adapters import GitAddAdapter


def repository(tmp_path: Path) -> Path:
    root = tmp_path / "repository"
    root.mkdir()
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    return root


def arguments(adapter: GitAddAdapter, paths: tuple[str, ...]) -> dict[str, object]:
    state = adapter.inspect(paths)
    return {
        "paths": state["paths"],
        "expected_index_digest": state["before_index_digest"],
        "expected_worktree_digest": state["before_worktree_state_digest"],
        "expected_staged_state_digest": state["before_staged_state_digest"],
    }


def test_git_add_input_is_immutable_and_rejects_non_exact_paths() -> None:
    value = GitAddInput(["notes/a.txt"])
    assert value.paths == ("notes/a.txt",)
    with pytest.raises(FrozenInstanceError):
        value.paths = ("other.txt",)  # type: ignore[misc]
    for paths in (
        (),
        (".",),
        ("-A",),
        ("*.txt",),
        ("../a.txt",),
        ("/a.txt",),
        (".git/config",),
        ("a.txt", "a.txt"),
    ):
        with pytest.raises(ValueError):
            GitAddInput(paths)


def test_git_add_uses_fixed_vector_and_stages_only_approved_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = repository(tmp_path)
    (root / "approved.txt").write_text("approved\n", encoding="utf-8")
    (root / "other.txt").write_text("other\n", encoding="utf-8")
    adapter = GitAddAdapter(root)
    request = ToolExecutionRequest("git", "add", arguments(adapter, ("approved.txt",)))
    original = subprocess.run
    calls: list[tuple[list[str], dict[str, object]]] = []

    def spy(command: list[str], **kwargs: object):
        calls.append((command, kwargs))
        return original(command, **kwargs)

    monkeypatch.setattr(subprocess, "run", spy)
    result = adapter.execute(request)
    staged = subprocess.run(
        ["git", "-C", str(root), "diff", "--cached", "--name-only"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.splitlines()

    add_call = next(item for item in calls if "add" in item[0])
    assert add_call[0][-3:] == ["add", "--", "approved.txt"]
    assert add_call[1]["shell"] is False
    assert add_call[1]["cwd"] == root
    assert staged == ["approved.txt"]
    assert result.mutation_performed is True
    assert not (root / "other.txt").is_symlink()


def test_git_add_rejects_stale_binary_symlink_directory_and_ignored_targets(
    tmp_path: Path,
) -> None:
    root = repository(tmp_path)
    (root / ".gitignore").write_text("ignored.txt\n", encoding="utf-8")
    (root / "ignored.txt").write_text("ignored\n", encoding="utf-8")
    (root / "binary.txt").write_bytes(b"a\x00b")
    (root / "folder").mkdir()
    outside = tmp_path / "outside.txt"
    outside.write_text("outside", encoding="utf-8")
    (root / "link.txt").symlink_to(outside)
    adapter = GitAddAdapter(root)
    for path in ("ignored.txt", "binary.txt", "folder", "link.txt"):
        with pytest.raises(ToolExecutionError):
            adapter.inspect((path,))

    (root / "valid.txt").write_text("before\n", encoding="utf-8")
    bound = arguments(adapter, ("valid.txt",))
    (root / "valid.txt").write_text("after\n", encoding="utf-8")
    with pytest.raises(ToolExecutionError, match="changed"):
        adapter.verify_preview(bound)
    assert (
        subprocess.run(
            ["git", "-C", str(root), "diff", "--cached", "--quiet"], check=False
        ).returncode
        == 0
    )
