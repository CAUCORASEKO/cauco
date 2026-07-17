from pathlib import Path

import pytest

from cauco_core.memory.exceptions import (
    InvalidMemoryPathError,
    MemoryFileNotFoundError,
    MemoryFileTooLargeError,
    MemoryPathTraversalError,
)
from cauco_core.memory.service import MemoryService


def test_recursive_discovery_is_stable_and_ignores_non_markdown_and_hidden(tmp_path: Path) -> None:
    brain = tmp_path / "brain"
    (brain / "zeta").mkdir(parents=True)
    (brain / "alpha").mkdir()
    (brain / ".obsidian").mkdir()
    (brain / "zeta" / "Z.md").write_text("# Zed\n", encoding="utf-8")
    (brain / "alpha" / "a.MD").write_text("# Alpha\n", encoding="utf-8")
    (brain / "ignore.txt").write_text("ignore", encoding="utf-8")
    (brain / ".hidden.md").write_text("# Hidden", encoding="utf-8")
    (brain / ".obsidian" / "private.md").write_text("# Private", encoding="utf-8")

    files = MemoryService(brain).list_markdown_files()
    assert [item.relative_path for item in files] == ["alpha/a.MD", "zeta/Z.md"]
    assert [item.title for item in files] == ["Alpha", "Zed"]


def test_utf8_reading_and_first_heading_title(tmp_path: Path) -> None:
    brain = tmp_path / "brain"
    brain.mkdir()
    (brain / "people.md").write_text("Intro\n## Henkilöt 👋\nJosé", encoding="utf-8")
    memory_file = MemoryService(brain).read_file("people.md")
    assert memory_file.title == "Henkilöt 👋"
    assert "José" in memory_file.content
    assert memory_file.modified_at is not None


@pytest.mark.parametrize("path", ["../secret.md", "/tmp/secret.md", ".obsidian/x.md", "note.txt"])
def test_unsafe_paths_are_rejected(tmp_path: Path, path: str) -> None:
    brain = tmp_path / "brain"
    brain.mkdir()
    with pytest.raises(InvalidMemoryPathError):
        MemoryService(brain).read_file(path)


def test_missing_file_returns_domain_error(tmp_path: Path) -> None:
    brain = tmp_path / "brain"
    brain.mkdir()
    with pytest.raises(MemoryFileNotFoundError):
        MemoryService(brain).read_file("missing.md")


def test_oversized_file_is_listed_but_cannot_be_read(tmp_path: Path) -> None:
    brain = tmp_path / "brain"
    brain.mkdir()
    (brain / "large.md").write_text("x" * 20, encoding="utf-8")
    service = MemoryService(brain, max_file_size=10)
    assert service.list_markdown_files()[0].relative_path == "large.md"
    with pytest.raises(MemoryFileTooLargeError, match="10-byte"):
        service.read_file("large.md")


def test_symlink_escape_is_not_discovered_or_read(tmp_path: Path) -> None:
    brain = tmp_path / "brain"
    brain.mkdir()
    outside = tmp_path / "outside.md"
    outside.write_text("# Secret", encoding="utf-8")
    (brain / "escape.md").symlink_to(outside)
    service = MemoryService(brain)
    assert service.list_markdown_files() == []
    with pytest.raises(MemoryPathTraversalError):
        service.read_file("escape.md")


def test_invalid_utf8_file_is_skipped_cleanly(tmp_path: Path) -> None:
    brain = tmp_path / "brain"
    brain.mkdir()
    (brain / "broken.md").write_bytes(b"\xff\xfe")
    assert MemoryService(brain).list_markdown_files() == []
