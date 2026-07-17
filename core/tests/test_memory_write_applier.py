import os
import stat
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import Mock

import pytest

from cauco_core.memory.engine import MemoryEngine
from cauco_core.memory.exceptions import MemoryPathTraversalError
from cauco_core.memory_writing.applier import (
    DuplicateMemoryContentError,
    InvalidProposalIntegrityError,
    MemoryWriteProposalApplier,
    MissingApprovedSectionError,
)
from cauco_core.memory_writing.models import (
    MemoryWriteOperation,
    MemoryWriteProposalState,
    MemoryWriteRequest,
)
from cauco_core.memory_writing.proposal_builder import MemoryWriteProposalBuilder
from cauco_core.memory_writing.store import (
    MemoryWriteProposalStore,
    ProposalStateConflictError,
)

FIXED_TIME = datetime(2026, 7, 17, 12, 0, tzinfo=UTC)


def memory_files() -> dict[str, str]:
    return {
        "Tasks.md": (
            "# Tasks\n\n## Today\n\n- [ ] Existing today\n\n"
            "## This Week\n\n- [ ] Existing week\n\n## Backlog\n"
        ),
        "Decisions.md": "# Decisions\n\n## Decision Log\n\nExisting rationale.\n",
        "Relationships.md": "# Relationships\n\n## Personal Notes\n",
        "Projects.md": "# Projects\n\n### Cauco\n\nExisting note.\n\n### Project Notes\n",
    }


def write_brain(tmp_path: Path) -> Path:
    brain = tmp_path / "brain"
    brain.mkdir()
    for name, content in memory_files().items():
        (brain / name).write_text(content, encoding="utf-8")
    return brain


def components(
    tmp_path: Path,
) -> tuple[
    MemoryWriteProposalBuilder,
    MemoryWriteProposalStore,
    MemoryWriteProposalApplier,
    MemoryEngine,
    Path,
]:
    brain = write_brain(tmp_path)
    engine = MemoryEngine(brain)
    engine.refresh()
    store = MemoryWriteProposalStore(clock=lambda: FIXED_TIME)
    builder = MemoryWriteProposalBuilder(engine, clock=lambda: FIXED_TIME)
    applier = MemoryWriteProposalApplier(engine, store, clock=lambda: FIXED_TIME)
    return builder, store, applier, engine, brain


def stored_proposal(
    builder: MemoryWriteProposalBuilder,
    store: MemoryWriteProposalStore,
    request: MemoryWriteRequest,
):
    proposal = builder.build(request)
    store.put(proposal)
    return proposal


def test_task_application_is_atomic_backed_up_and_refreshes(tmp_path: Path) -> None:
    builder, store, applier, engine, brain = components(tmp_path)
    target = brain / "Tasks.md"
    original = target.read_bytes()
    os.chmod(target, 0o640)
    original_refresh = engine.refresh
    engine.refresh = Mock(wraps=original_refresh)
    proposal = stored_proposal(
        builder,
        store,
        MemoryWriteRequest(instruction="Tomorrow I need to finish the plugin"),
    )

    result = applier.apply(proposal.proposal_id)

    content = target.read_text(encoding="utf-8")
    this_week = content.split("## This Week", 1)[1].split("## Backlog", 1)[0]
    today = content.split("## Today", 1)[1].split("## This Week", 1)[0]
    assert proposal.markdown_preview in this_week
    assert proposal.markdown_preview not in today
    assert result.memory_refreshed is True
    assert result.state is MemoryWriteProposalState.APPLIED
    assert store.get(proposal.proposal_id).applied_at == FIXED_TIME
    engine.refresh.assert_called_once()
    assert (brain / "Tasks.md.bak").read_bytes() == original
    assert stat.S_IMODE(target.stat().st_mode) == 0o640
    assert not list(brain.glob(".*.tmp"))


def test_atomic_insertion_preserves_crlf_newlines(tmp_path: Path) -> None:
    builder, store, applier, _, brain = components(tmp_path)
    target = brain / "Tasks.md"
    target.write_bytes(target.read_bytes().replace(b"\n", b"\r\n"))
    proposal = stored_proposal(
        builder,
        store,
        MemoryWriteRequest(instruction="Today I need to preserve newlines"),
    )
    applier.apply(proposal.proposal_id)
    result = target.read_bytes()
    assert b"\r\n" in result
    assert b"\n" not in result.replace(b"\r\n", b"")


def test_task_today_and_backlog_insertions_use_correct_sections(tmp_path: Path) -> None:
    builder, store, applier, engine, brain = components(tmp_path)
    today = stored_proposal(
        builder,
        store,
        MemoryWriteRequest(instruction="Today I need to call Ville"),
    )
    applier.apply(today.proposal_id)

    backlog = builder.build(
        MemoryWriteRequest(
            instruction="Someday I should review notes",
            operation=MemoryWriteOperation.ADD_TASK,
        )
    )
    store.put(backlog)
    applier.apply(backlog.proposal_id)

    content = (brain / "Tasks.md").read_text(encoding="utf-8")
    today_section = content.split("## Today", 1)[1].split("## This Week", 1)[0]
    backlog_section = content.split("## Backlog", 1)[1]
    assert today.markdown_preview in today_section
    assert backlog.markdown_preview in backlog_section
    task_id = next(item.id for item in engine.list_objects() if item.name == "Tasks.md")
    assert engine.get_object(task_id)


@pytest.mark.parametrize(
    ("write_request", "filename", "section"),
    [
        (
            MemoryWriteRequest(
                instruction="Record the decision that writes require review",
                operation=MemoryWriteOperation.ADD_DECISION,
            ),
            "Decisions.md",
            "Decision Log",
        ),
        (
            MemoryWriteRequest(
                instruction="Add a note that Ville works at Aalto",
                operation=MemoryWriteOperation.ADD_RELATIONSHIP_NOTE,
            ),
            "Relationships.md",
            "Personal Notes",
        ),
        (
            MemoryWriteRequest(
                instruction="Add to the Cauco project that Phase 4 is active",
                operation=MemoryWriteOperation.ADD_PROJECT_NOTE,
            ),
            "Projects.md",
            "Cauco",
        ),
    ],
)
def test_approved_operation_inserts_only_into_its_target(
    tmp_path: Path,
    write_request: MemoryWriteRequest,
    filename: str,
    section: str,
) -> None:
    builder, store, applier, _, brain = components(tmp_path)
    before = {name: (brain / name).read_bytes() for name in memory_files()}
    proposal = stored_proposal(builder, store, write_request)
    result = applier.apply(proposal.proposal_id)
    assert proposal.markdown_preview in (brain / filename).read_text(encoding="utf-8")
    assert result.target_section == section
    for other_name, original in before.items():
        if other_name != filename:
            assert (brain / other_name).read_bytes() == original


def test_duplicate_content_and_missing_section_fail_without_refresh(tmp_path: Path) -> None:
    builder, store, applier, engine, brain = components(tmp_path)
    duplicate = builder.build(MemoryWriteRequest(instruction="Add a task to duplicate"))
    tasks = brain / "Tasks.md"
    tasks.write_text(
        tasks.read_text(encoding="utf-8").replace(
            "## Today\n", f"## Today\n\n{duplicate.markdown_preview}\n"
        ),
        encoding="utf-8",
    )
    store.put(duplicate)
    engine.refresh = Mock(side_effect=AssertionError("refresh must not run"))
    with pytest.raises(DuplicateMemoryContentError):
        applier.apply(duplicate.proposal_id)
    engine.refresh.assert_not_called()
    assert store.get(duplicate.proposal_id).state is MemoryWriteProposalState.PENDING

    missing = builder.build(
        MemoryWriteRequest(
            instruction="Store a relationship note",
            operation=MemoryWriteOperation.ADD_RELATIONSHIP_NOTE,
        )
    )
    store.put(missing)
    (brain / "Relationships.md").write_text("# Relationships\n", encoding="utf-8")
    with pytest.raises(MissingApprovedSectionError):
        applier.apply(missing.proposal_id)
    engine.refresh.assert_not_called()


def test_project_fallback_requires_existing_project_notes_heading(tmp_path: Path) -> None:
    builder, store, applier, engine, brain = components(tmp_path)
    proposal = stored_proposal(
        builder,
        store,
        MemoryWriteRequest(
            instruction="Add a project note that Atlas is pending",
            operation=MemoryWriteOperation.ADD_PROJECT_NOTE,
            project="Atlas",
        ),
    )
    projects = brain / "Projects.md"
    original = projects.read_text(encoding="utf-8").replace("\n### Project Notes\n", "\n")
    projects.write_text(original, encoding="utf-8")
    engine.refresh = Mock(side_effect=AssertionError("refresh must not run"))
    with pytest.raises(MissingApprovedSectionError):
        applier.apply(proposal.proposal_id)
    assert projects.read_text(encoding="utf-8") == original
    engine.refresh.assert_not_called()


def test_integrity_verification_blocks_mutated_stored_proposal(tmp_path: Path) -> None:
    builder, store, applier, engine, brain = components(tmp_path)
    proposal = stored_proposal(
        builder,
        store,
        MemoryWriteRequest(instruction="Add a task to verify integrity"),
    )
    original = (brain / "Tasks.md").read_bytes()
    store._records[proposal.proposal_id].proposal.markdown_preview = "- [ ] forged"
    engine.refresh = Mock(side_effect=AssertionError("refresh must not run"))
    with pytest.raises(InvalidProposalIntegrityError):
        applier.apply(proposal.proposal_id)
    assert (brain / "Tasks.md").read_bytes() == original
    engine.refresh.assert_not_called()


def test_symlink_escape_is_blocked(tmp_path: Path) -> None:
    builder, store, applier, engine, brain = components(tmp_path)
    proposal = stored_proposal(
        builder,
        store,
        MemoryWriteRequest(instruction="Add a task to block symlinks"),
    )
    outside = tmp_path / "outside.md"
    outside.write_text("# Outside\n\n## Today\n", encoding="utf-8")
    (brain / "Tasks.md").unlink()
    (brain / "Tasks.md").symlink_to(outside)
    engine.refresh = Mock(side_effect=AssertionError("refresh must not run"))
    with pytest.raises(MemoryPathTraversalError):
        applier.apply(proposal.proposal_id)
    assert outside.read_text(encoding="utf-8") == "# Outside\n\n## Today\n"
    engine.refresh.assert_not_called()


def test_refresh_failure_reports_applied_partial_success(tmp_path: Path) -> None:
    builder, store, applier, engine, brain = components(tmp_path)
    proposal = stored_proposal(
        builder,
        store,
        MemoryWriteRequest(instruction="Add a task to survive refresh failure"),
    )
    engine.refresh = Mock(side_effect=RuntimeError("private refresh failure"))
    result = applier.apply(proposal.proposal_id)
    assert result.memory_refreshed is False
    assert result.warnings == ["Memory was written, but the Memory Engine refresh failed."]
    assert proposal.markdown_preview in (brain / "Tasks.md").read_text(encoding="utf-8")
    assert store.get(proposal.proposal_id).state is MemoryWriteProposalState.APPLIED


def test_concurrent_confirmation_applies_exactly_once(tmp_path: Path) -> None:
    builder, store, applier, _, brain = components(tmp_path)
    proposal = stored_proposal(
        builder,
        store,
        MemoryWriteRequest(instruction="Add a task to apply once"),
    )

    def confirm() -> str:
        try:
            applier.apply(proposal.proposal_id)
            return "applied"
        except ProposalStateConflictError:
            return "conflict"

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = sorted(executor.map(lambda _: confirm(), range(2)))
    assert outcomes == ["applied", "conflict"]
    assert (brain / "Tasks.md").read_text(encoding="utf-8").count(
        proposal.markdown_preview
    ) == 1
