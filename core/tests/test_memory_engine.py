from pathlib import Path

import pytest

from cauco_core.memory.classifier import classify_memory
from cauco_core.memory.engine import MemoryEngine
from cauco_core.memory.exceptions import MemoryDirectoryError
from cauco_core.memory.models import MemoryKind, MemoryLayer


@pytest.mark.parametrize(
    ("filename", "kind", "layer"),
    [
        ("Bienvenido.md", MemoryKind.IDENTITY, MemoryLayer.IDENTITY),
        ("Projects.md", MemoryKind.PROJECTS, MemoryLayer.LONG_TERM),
        ("Tasks.md", MemoryKind.TASKS, MemoryLayer.WORKING),
        ("Decisions.md", MemoryKind.DECISIONS, MemoryLayer.LONG_TERM),
        ("Relationships.md", MemoryKind.RELATIONSHIPS, MemoryLayer.LONG_TERM),
        ("Memory Rules.md", MemoryKind.RULES, MemoryLayer.GOVERNANCE),
    ],
)
def test_canonical_filename_classification(
    filename: str, kind: MemoryKind, layer: MemoryLayer
) -> None:
    result = classify_memory(filename, Path(filename).stem, "")
    assert (result.kind, result.layer) == (kind, layer)
    assert result.confidence == 0.95


def test_people_legacy_alias_is_relationships() -> None:
    result = classify_memory("People.md", "People", "# People")
    assert result.kind is MemoryKind.RELATIONSHIPS
    assert result.layer is MemoryLayer.LONG_TERM


def test_front_matter_overrides_other_classification_signals() -> None:
    content = """---
memory_kind: research
memory_layer: session
owner: local
---
# Tasks
"""
    result = classify_memory("Tasks.md", "Tasks", content)
    assert result.kind is MemoryKind.RESEARCH
    assert result.layer is MemoryLayer.SESSION
    assert result.confidence == 1.0
    assert result.front_matter["owner"] == "local"


@pytest.mark.parametrize(
    ("relative_path", "kind", "layer"),
    [
        ("Daily/2026-07-17.md", MemoryKind.DAILY, MemoryLayer.WORKING),
        ("Meetings/standup.md", MemoryKind.MEETINGS, MemoryLayer.WORKING),
        ("Research/local-models.md", MemoryKind.RESEARCH, MemoryLayer.LONG_TERM),
        ("Reports/weekly.md", MemoryKind.REPORTS, MemoryLayer.LONG_TERM),
    ],
)
def test_directory_classification(
    relative_path: str, kind: MemoryKind, layer: MemoryLayer
) -> None:
    result = classify_memory(relative_path, "Untitled", "")
    assert (result.kind, result.layer) == (kind, layer)


def test_archive_directory_overrides_inferred_layer() -> None:
    result = classify_memory("Archive/Tasks.md", "Tasks", "# Tasks")
    assert result.kind is MemoryKind.TASKS
    assert result.layer is MemoryLayer.ARCHIVE


def test_general_markdown_fallback_is_long_term() -> None:
    result = classify_memory("Notes/Small idea.md", "Small idea", "A local note.")
    assert result.kind is MemoryKind.GENERAL
    assert result.layer is MemoryLayer.LONG_TERM


def test_engine_discovers_safely_and_ids_are_stable(tmp_path: Path) -> None:
    brain = tmp_path / "brain"
    (brain / "nested").mkdir(parents=True)
    (brain / ".obsidian").mkdir()
    (brain / "nested" / "Projects.md").write_text("# Projects\nAtlas", encoding="utf-8")
    (brain / "Tasks.md").write_text("# Tasks\n- [ ] Test", encoding="utf-8")
    (brain / ".hidden.md").write_text("secret", encoding="utf-8")
    (brain / ".obsidian" / "private.md").write_text("secret", encoding="utf-8")
    (brain / "nested" / "ignore.txt").write_text("ignore", encoding="utf-8")

    engine = MemoryEngine(brain)
    first_status = engine.refresh()
    first_ids = [item.id for item in engine.list_objects()]
    second_status = engine.refresh()

    assert first_status.summary.total == second_status.summary.total == 2
    assert [item.relative_path for item in engine.list_objects()] == [
        "nested/Projects.md",
        "Tasks.md",
    ]
    assert [item.id for item in engine.list_objects()] == first_ids
    assert all(item.path == item.relative_path for item in engine.list_objects())


def test_registry_filters_and_summary(tmp_path: Path) -> None:
    brain = tmp_path / "brain"
    (brain / "Meetings").mkdir(parents=True)
    (brain / "Tasks.md").write_text("# Tasks", encoding="utf-8")
    (brain / "Meetings" / "sync.md").write_text("# Sync", encoding="utf-8")
    engine = MemoryEngine(brain)
    engine.refresh()

    assert [item.relative_path for item in engine.get_by_kind(MemoryKind.TASKS)] == [
        "Tasks.md"
    ]
    assert [item.relative_path for item in engine.get_by_layer(MemoryLayer.WORKING)] == [
        "Meetings/sync.md",
        "Tasks.md",
    ]
    summary = engine.summary()
    assert summary.total == 2
    assert summary.by_kind[MemoryKind.TASKS] == 1
    assert summary.by_kind[MemoryKind.MEETINGS] == 1
    assert summary.by_layer[MemoryLayer.WORKING] == 2


def test_unreadable_markdown_does_not_break_refresh(tmp_path: Path) -> None:
    brain = tmp_path / "brain"
    brain.mkdir()
    (brain / "broken.md").write_bytes(b"\xff\xfe")
    (brain / "Projects.md").write_text("# Projects", encoding="utf-8")
    engine = MemoryEngine(brain)
    assert engine.refresh().summary.total == 1


def test_invalid_brain_directory_marks_engine_unavailable(tmp_path: Path) -> None:
    invalid_brain = tmp_path / "brain.md"
    invalid_brain.write_text("not a directory", encoding="utf-8")
    engine = MemoryEngine(invalid_brain)
    with pytest.raises(MemoryDirectoryError):
        engine.refresh()
    assert engine.status().status == "unavailable"
