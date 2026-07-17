from datetime import UTC, datetime
from pathlib import Path

import pytest

from cauco_core.context.analyzer import IntentAnalyzer
from cauco_core.context.builder import ContextBuilder
from cauco_core.context.models import ContextIntent
from cauco_core.memory.engine import MemoryEngine
from cauco_core.memory.models import MemoryKind, MemoryLayer

FIXED_TIME = datetime(2026, 7, 17, 12, 0, tzinfo=UTC)


def populated_engine(tmp_path: Path) -> MemoryEngine:
    brain = tmp_path / "brain"
    brain.mkdir()
    documents = {
        "Bienvenido.md": "# Bienvenido\nLocal identity.",
        "Projects.md": "# Projects\nCauco.",
        "Tasks.md": "# Tasks\n- [ ] Context builder.",
        "Decisions.md": "# Decisions\nUse Obsidian for local notes.",
        "Relationships.md": "# Relationships\nVille is a collaborator.",
        "Memory Rules.md": "# Memory Rules\nMemory stays local.",
        "note.md": "# A note\nUnclassified context.",
    }
    for relative_path, content in documents.items():
        (brain / relative_path).write_text(content, encoding="utf-8")
    engine = MemoryEngine(brain)
    engine.refresh()
    return engine


@pytest.mark.parametrize(
    ("question", "expected"),
    [
        ("What should I work on today?", ContextIntent.PLANNING),
        ("What projects am I working on?", ContextIntent.PROJECT),
        ("Who is Ville?", ContextIntent.RELATIONSHIP),
        ("Why are we using Obsidian?", ContextIntent.DECISION),
        ("Who am I?", ContextIntent.IDENTITY),
        ("Please explain this", ContextIntent.GENERAL),
        ("Research local language models", ContextIntent.RESEARCH),
        ("What is the meeting agenda?", ContextIntent.MEETING),
        ("Prepare a weekly report", ContextIntent.REPORT),
    ],
)
def test_deterministic_intent_detection(question: str, expected: ContextIntent) -> None:
    assert IntentAnalyzer().analyze(question).intent is expected


def test_planning_selects_tasks_and_projects_with_reasoning(tmp_path: Path) -> None:
    package = ContextBuilder(
        populated_engine(tmp_path),
        clock=lambda: FIXED_TIME,
    ).build("What should I work on today?")

    assert package.detected_intent is ContextIntent.PLANNING
    assert package.selected_layers == [MemoryLayer.WORKING, MemoryLayer.LONG_TERM]
    assert package.selected_kinds == [MemoryKind.TASKS, MemoryKind.PROJECTS]
    assert [item.relative_path for item in package.selected_memory_objects] == [
        "Projects.md",
        "Tasks.md",
    ]
    assert package.reasoning == [
        "Detected planning intent from: what should i, work on today, today.",
        "Selected Working Memory for current actions.",
        "Added Tasks.",
        "Added Projects for active context.",
    ]


@pytest.mark.parametrize(
    ("question", "expected_paths"),
    [
        ("What projects am I working on?", ["Projects.md", "Tasks.md"]),
        ("Who is Ville?", ["Relationships.md"]),
        (
            "Why are we using Obsidian?",
            ["Decisions.md", "Memory Rules.md", "Projects.md"],
        ),
        ("How does memory work?", ["Decisions.md", "Memory Rules.md", "Projects.md"]),
        ("Who am I?", ["Bienvenido.md"]),
        ("Please explain this", ["note.md"]),
    ],
)
def test_memory_selection_by_intent(
    tmp_path: Path,
    question: str,
    expected_paths: list[str],
) -> None:
    package = ContextBuilder(populated_engine(tmp_path)).build(question)
    assert [item.relative_path for item in package.selected_memory_objects] == expected_paths
    assert all("content" not in item.model_dump() for item in package.selected_memory_objects)


def test_build_is_deterministic_with_a_fixed_clock(tmp_path: Path) -> None:
    builder = ContextBuilder(populated_engine(tmp_path), clock=lambda: FIXED_TIME)
    first = builder.build("Who is Ville?")
    second = builder.build("Who is Ville?")
    assert first == second
    assert first.generated_at == FIXED_TIME


def test_no_match_is_explained(tmp_path: Path) -> None:
    brain = tmp_path / "empty-brain"
    brain.mkdir()
    engine = MemoryEngine(brain)
    engine.refresh()
    package = ContextBuilder(engine).build("Who is Ville?")
    assert package.selected_memory_objects == []
    assert package.reasoning[-1] == "No classified memory objects matched the selection rules."
