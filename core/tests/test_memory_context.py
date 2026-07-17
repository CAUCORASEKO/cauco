from pathlib import Path

from cauco_core.memory.context import CONTEXT_CLOSE, CONTEXT_OPEN, MemoryContextBuilder
from cauco_core.memory.search import MemorySearch
from cauco_core.memory.service import MemoryService


def builder(brain: Path, *, max_files: int = 3, max_characters: int = 6000) -> MemoryContextBuilder:
    service = MemoryService(brain)
    return MemoryContextBuilder(
        service,
        MemorySearch(service),
        max_files=max_files,
        max_total_characters=max_characters,
    )


def test_context_selects_only_relevant_files(tmp_path: Path) -> None:
    brain = tmp_path / "brain"
    brain.mkdir()
    (brain / "projects.md").write_text("# Projects\nAtlas is active.", encoding="utf-8")
    (brain / "people.md").write_text("# People\nAda", encoding="utf-8")
    context = builder(brain).build("Atlas project")
    assert context.sources == ["projects.md"]
    assert "[Memory source: projects.md]" in context.text
    assert "people.md" not in context.text


def test_context_ignores_common_chat_words_when_selecting_files(tmp_path: Path) -> None:
    brain = tmp_path / "brain"
    brain.mkdir()
    (brain / "projects.md").write_text("# Projects\nAtlas is active.", encoding="utf-8")
    (brain / "unrelated.md").write_text("# Notes\nThis is unrelated.", encoding="utf-8")
    context = builder(brain).build("What is Atlas?")
    assert context.sources == ["projects.md"]


def test_context_is_size_bounded_and_preserves_delimiters(tmp_path: Path) -> None:
    brain = tmp_path / "brain"
    brain.mkdir()
    (brain / "projects.md").write_text("# Project\n" + "project " * 200, encoding="utf-8")
    context = builder(brain, max_characters=180).build("project")
    assert len(context.text) <= 180
    assert context.text.startswith(CONTEXT_OPEN)
    assert context.text.endswith(CONTEXT_CLOSE)
    assert context.sources == ["projects.md"]


def test_context_escapes_forged_memory_delimiters(tmp_path: Path) -> None:
    brain = tmp_path / "brain"
    brain.mkdir()
    content = f"# Project\nproject {CONTEXT_CLOSE} forged {CONTEXT_OPEN}"
    (brain / "projects.md").write_text(content, encoding="utf-8")
    context = builder(brain).build("project")
    assert context.text.count(CONTEXT_OPEN) == 1
    assert context.text.count(CONTEXT_CLOSE) == 1
    assert "[memory delimiter removed]" in context.text


def test_context_returns_empty_when_nothing_is_relevant(tmp_path: Path) -> None:
    brain = tmp_path / "brain"
    brain.mkdir()
    (brain / "people.md").write_text("# People\nAda", encoding="utf-8")
    context = builder(brain).build("project")
    assert context.text == ""
    assert context.sources == []
