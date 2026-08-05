from datetime import UTC, date, datetime
from pathlib import Path
from unittest.mock import Mock

import pytest

from cauco_core.memory.engine import MemoryEngine
from cauco_core.memory.models import MemoryKind, MemoryLayer
from cauco_core.memory_writing.analyzer import (
    MemoryWriteProposalError,
    UnsafeMemoryWriteInstructionError,
    UnsupportedMemoryWriteOperationError,
)
from cauco_core.memory_writing.models import MemoryWriteOperation, MemoryWriteRequest
from cauco_core.memory_writing.proposal_builder import MemoryWriteProposalBuilder

FIXED_TIME = datetime(2026, 7, 17, 12, 30, tzinfo=UTC)


def proposal_builder(tmp_path: Path) -> tuple[MemoryWriteProposalBuilder, MemoryEngine, Path]:
    brain = tmp_path / "brain"
    brain.mkdir()
    (brain / "Projects.md").write_text(
        "# Projects\n\n## Cauco\n\nLocal brain project.\n\n## Other\n",
        encoding="utf-8",
    )
    (brain / "Tasks.md").write_text("# Tasks\n", encoding="utf-8")
    engine = MemoryEngine(brain)
    engine.refresh()
    return MemoryWriteProposalBuilder(engine, clock=lambda: FIXED_TIME), engine, brain


def test_task_proposal_is_normalized_and_requires_confirmation(tmp_path: Path) -> None:
    builder, _, _ = proposal_builder(tmp_path)
    proposal = builder.build(
        MemoryWriteRequest(instruction="Remember that tomorrow I must finish the plugin.")
    )
    assert proposal.operation is MemoryWriteOperation.ADD_TASK
    assert proposal.target_file == "Tasks.md"
    assert proposal.target_kind is MemoryKind.TASKS
    assert proposal.target_layer is MemoryLayer.WORKING
    assert proposal.target_section == "This Week"
    assert proposal.normalized_content == "Finish the plugin tomorrow"
    assert proposal.markdown_preview == "- [ ] Finish the plugin tomorrow"
    assert proposal.requires_confirmation is True


def test_decision_proposal_has_structured_preview(tmp_path: Path) -> None:
    builder, _, _ = proposal_builder(tmp_path)
    proposal = builder.build(
        MemoryWriteRequest(
            instruction=(
                "Record the decision that memory writes require confirmation "
                "because users retain control impact: unsafe writes are prevented."
            ),
            requested_date=date(2026, 7, 18),
        )
    )
    assert proposal.operation is MemoryWriteOperation.ADD_DECISION
    assert proposal.target_file == "Decisions.md"
    assert proposal.target_section == "Decision Log"
    assert proposal.normalized_content == "Memory writes require confirmation"
    assert "- **Date:** 2026-07-18" in proposal.markdown_preview
    assert "**Reason:** Users retain control" in proposal.markdown_preview
    assert "**Impact:** Unsafe writes are prevented" in proposal.markdown_preview
    assert proposal.warnings == []


def test_relationship_note_proposal_includes_person(tmp_path: Path) -> None:
    builder, _, _ = proposal_builder(tmp_path)
    proposal = builder.build(
        MemoryWriteRequest(instruction="Add a note that Ville works at Aalto.")
    )
    assert proposal.operation is MemoryWriteOperation.ADD_RELATIONSHIP_NOTE
    assert proposal.target_file == "Relationships.md"
    assert proposal.target_section == "Personal Notes"
    assert proposal.normalized_content == "Ville works at Aalto"
    assert proposal.markdown_preview == "- **Ville:** Works at Aalto"


def test_project_note_uses_matching_existing_heading(tmp_path: Path) -> None:
    builder, _, _ = proposal_builder(tmp_path)
    proposal = builder.build(
        MemoryWriteRequest(instruction="Add to the Cauco project that Phase 3 is complete.")
    )
    assert proposal.operation is MemoryWriteOperation.ADD_PROJECT_NOTE
    assert proposal.target_file == "Projects.md"
    assert proposal.target_section == "Cauco"
    assert proposal.normalized_content == "Phase 3 is complete"
    assert proposal.markdown_preview == "- **Cauco:** Phase 3 is complete"
    assert proposal.warnings == []


def test_project_note_uses_safe_fallback_for_unknown_project(tmp_path: Path) -> None:
    builder, _, _ = proposal_builder(tmp_path)
    proposal = builder.build(
        MemoryWriteRequest(
            instruction="Add a project note that the launch is pending.",
            project="Atlas",
        )
    )
    assert proposal.target_section == "Project Notes"
    assert proposal.markdown_preview == "- **Atlas:** The launch is pending"
    assert proposal.warnings == [
        "No existing project heading matched 'Atlas'; using Project Notes."
    ]


def test_explicit_operation_is_used_without_inference(tmp_path: Path) -> None:
    builder, _, _ = proposal_builder(tmp_path)
    proposal = builder.build(
        MemoryWriteRequest(
            instruction="Capture that Ada prefers concise updates.",
            operation=MemoryWriteOperation.ADD_RELATIONSHIP_NOTE,
            person="Ada",
        )
    )
    assert proposal.operation is MemoryWriteOperation.ADD_RELATIONSHIP_NOTE
    assert proposal.reasoning[0] == "Used explicit supported operation: add_relationship_note."


@pytest.mark.parametrize(
    ("instruction", "operation"),
    [
        ("I need to prepare the release", MemoryWriteOperation.ADD_TASK),
        ("Record the decision that local data stays local", MemoryWriteOperation.ADD_DECISION),
        ("Remember that Ada works at Aalto", MemoryWriteOperation.ADD_RELATIONSHIP_NOTE),
        ("The Cauco project reached a milestone", MemoryWriteOperation.ADD_PROJECT_NOTE),
    ],
)
def test_operation_inference_is_deterministic(
    tmp_path: Path,
    instruction: str,
    operation: MemoryWriteOperation,
) -> None:
    builder, _, _ = proposal_builder(tmp_path)
    assert builder.build(MemoryWriteRequest(instruction=instruction)).operation is operation


@pytest.mark.parametrize(
    ("instruction", "section"),
    [
        ("Add a task to call Ville", "Today"),
        ("Today I need to call Ville", "Today"),
        ("Tomorrow I need to call Ville", "This Week"),
        ("This week I need to finish the API", "This Week"),
        ("Add this task to the backlog: review old notes", "Backlog"),
        ("Someday I should review the archive", "Backlog"),
        ("This is not urgent, add a task to review it later", "Backlog"),
    ],
)
def test_task_section_selection(tmp_path: Path, instruction: str, section: str) -> None:
    builder, _, _ = proposal_builder(tmp_path)
    proposal = builder.build(
        MemoryWriteRequest(instruction=instruction, operation=MemoryWriteOperation.ADD_TASK)
    )
    assert proposal.target_section == section


def test_supported_operations_use_only_approved_targets(tmp_path: Path) -> None:
    builder, _, _ = proposal_builder(tmp_path)
    actual = [(item.operation.value, item.target_file) for item in builder.supported_operations()]
    assert actual == [
        ("add_task", "Tasks.md"),
        ("add_decision", "Decisions.md"),
        ("add_relationship_note", "Relationships.md"),
        ("add_project_note", "Projects.md"),
    ]


def test_ambiguous_instruction_is_rejected(tmp_path: Path) -> None:
    builder, _, _ = proposal_builder(tmp_path)
    with pytest.raises(UnsupportedMemoryWriteOperationError):
        builder.build(MemoryWriteRequest(instruction="Remember this information"))


@pytest.mark.parametrize(
    "instruction",
    [
        "Add a task to write ../private.md",
        "Add a task to write /tmp/private",
        "Add a task to write C:\\private\\note",
        "Add a task directly to Secrets.md",
        "---\nmemory_kind: tasks\n---\nAdd a task",
        "Add a task <script>alert('x')</script>",
        "Add a task without confirmation",
        "Add a task with a null byte\x00here",
    ],
)
def test_unsafe_instruction_is_rejected(tmp_path: Path, instruction: str) -> None:
    builder, _, _ = proposal_builder(tmp_path)
    with pytest.raises(UnsafeMemoryWriteInstructionError):
        builder.build(MemoryWriteRequest(instruction=instruction))


@pytest.mark.parametrize(
    "operation",
    [
        operation
        for operation in MemoryWriteOperation
        if operation is not MemoryWriteOperation.ADD_LEARNING_NOTE
    ],
)
def test_confirmation_is_required_for_every_public_operation(
    tmp_path: Path,
    operation: MemoryWriteOperation,
) -> None:
    builder, _, _ = proposal_builder(tmp_path)
    proposal = builder.build(
        MemoryWriteRequest(
            instruction="Store this safe note",
            operation=operation,
        )
    )
    assert proposal.requires_confirmation is True


def test_public_builder_rejects_internal_learning_note_operation(
    tmp_path: Path,
) -> None:
    builder, _, _ = proposal_builder(tmp_path)

    with pytest.raises(
        MemoryWriteProposalError,
        match="only be created from approved memory candidates",
    ):
        builder.build(
            MemoryWriteRequest(
                instruction="Store this safe learning note",
                operation=MemoryWriteOperation.ADD_LEARNING_NOTE,
            )
        )


def test_proposal_does_not_modify_files_or_refresh_engine(tmp_path: Path) -> None:
    builder, engine, brain = proposal_builder(tmp_path)
    before = {path.name: path.read_bytes() for path in brain.iterdir()}
    engine.refresh = Mock(side_effect=AssertionError("refresh must not be called"))

    builder.build(MemoryWriteRequest(instruction="Add a task to test the proposal"))

    after = {path.name: path.read_bytes() for path in brain.iterdir()}
    assert after == before
    engine.refresh.assert_not_called()


def test_proposal_is_deterministic_with_fixed_clock(tmp_path: Path) -> None:
    builder, _, _ = proposal_builder(tmp_path)
    request = MemoryWriteRequest(instruction="Add a task to finish the API")
    first = builder.build(request)
    second = builder.build(request)
    assert first == second
    assert first.proposal_id.startswith("proposal_")
    assert first.created_at == FIXED_TIME


def test_raw_heading_input_cannot_create_a_heading(tmp_path: Path) -> None:
    builder, _, _ = proposal_builder(tmp_path)
    proposal = builder.build(
        MemoryWriteRequest(
            instruction="Add a task to review this\n## Injected heading",
            operation=MemoryWriteOperation.ADD_TASK,
        )
    )
    assert proposal.markdown_preview.startswith("- [ ] ")
    assert "\n#" not in proposal.markdown_preview
