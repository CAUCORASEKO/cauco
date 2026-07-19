import subprocess
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from cauco_tools.adapters import FilesystemAdapter, GitStatusAdapter
from cauco_tools.execution import (
    ToolExecutionError,
    ToolExecutionRequest,
    ToolExecutionTimeoutError,
)


def git_workspace(tmp_path: Path) -> Path:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    subprocess.run(["git", "init", "-q", str(workspace)], check=True)
    (workspace / "README.md").write_text("# Example\n", encoding="utf-8")
    return workspace


def test_execution_request_is_immutable_and_bounded() -> None:
    request = ToolExecutionRequest("git", "status")
    with pytest.raises(FrozenInstanceError):
        request.operation_id = "commit"  # type: ignore[misc]
    with pytest.raises(TypeError):
        request.arguments["args"] = ["commit"]  # type: ignore[index]
    with pytest.raises(ValueError, match="timeout"):
        ToolExecutionRequest("git", "status", timeout_seconds=31)


def test_git_status_executes_fixed_vector_without_shell(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace = git_workspace(tmp_path)
    adapter = GitStatusAdapter(workspace)
    original = subprocess.run
    calls: list[dict[str, object]] = []

    def spy(*args: object, **kwargs: object):
        calls.append(kwargs)
        return original(*args, **kwargs)

    monkeypatch.setattr(subprocess, "run", spy)
    result = adapter.execute(ToolExecutionRequest("git", "status", max_output_chars=100))

    assert result.success is True
    assert result.execution_performed is True
    assert len(result.output) <= 100
    assert calls and calls[0]["shell"] is False
    assert calls[0]["cwd"] == workspace
    assert "README.md" in result.output
    with pytest.raises(ToolExecutionError, match="accepts no operation arguments"):
        adapter.execute(ToolExecutionRequest("git", "status", {"args": ["commit"]}))


def test_git_timeout_is_enforced(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    workspace = git_workspace(tmp_path)
    adapter = GitStatusAdapter(workspace)

    def timeout(*args: object, **kwargs: object):
        raise subprocess.TimeoutExpired(cmd="git", timeout=0.1)

    monkeypatch.setattr(subprocess, "run", timeout)
    with pytest.raises(ToolExecutionTimeoutError):
        adapter.execute(ToolExecutionRequest("git", "status", timeout_seconds=0.1))


def test_filesystem_listing_and_bounded_text_read(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "b.txt").write_text("bravo", encoding="utf-8")
    (workspace / "a.txt").write_text("alphabet", encoding="utf-8")
    (workspace / ".hidden").write_text("secret", encoding="utf-8")
    adapter = FilesystemAdapter(workspace)

    listing = adapter.execute(
        ToolExecutionRequest("filesystem", "list_directory", {"relative_path": "."})
    )
    reading = adapter.execute(
        ToolExecutionRequest(
            "filesystem", "read_file", {"relative_path": "a.txt", "max_chars": 5}
        )
    )

    assert [item["path"] for item in listing.structured_data["entries"]] == [
        "a.txt",
        "b.txt",
    ]
    assert reading.output == "alpha"
    assert reading.truncated is True
    assert reading.structured_data["path"] == "a.txt"


@pytest.mark.parametrize("path", ["../outside.txt", "/etc/passwd", ".env", ".ssh/id_rsa"])
def test_filesystem_rejects_traversal_absolute_and_sensitive_paths(
    tmp_path: Path, path: str
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / ".env").write_text("TOKEN=secret", encoding="utf-8")
    adapter = FilesystemAdapter(workspace)
    with pytest.raises(ToolExecutionError):
        adapter.execute(
            ToolExecutionRequest("filesystem", "read_file", {"relative_path": path})
        )


def test_filesystem_rejects_binary_oversize_and_symlink_escape(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "binary.bin").write_bytes(b"abc\x00def")
    (workspace / "large.txt").write_text("x" * 20, encoding="utf-8")
    outside = tmp_path / "outside.txt"
    outside.write_text("outside", encoding="utf-8")
    (workspace / "escape.txt").symlink_to(outside)
    adapter = FilesystemAdapter(workspace, max_file_bytes=10)

    for name in ("binary.bin", "large.txt", "escape.txt"):
        with pytest.raises(ToolExecutionError):
            adapter.execute(
                ToolExecutionRequest("filesystem", "read_file", {"relative_path": name})
            )
