from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from cauco_core.config import Settings
from cauco_core.learning.models import LessonCategory
from cauco_core.learning_guidance.models import LearningGuidance
from cauco_core.learning_guidance.resolver import LearningGuidanceResolver
from cauco_core.memory.engine import MemoryEngine
from cauco_core.memory_candidates.models import MemoryCandidateLesson
from cauco_core.memory_candidates.store import MemoryCandidateStore
from cauco_core.memory_writing.models import MemoryWriteProposalState
from cauco_core.memory_writing.proposal_builder import MemoryWriteProposalBuilder
from cauco_core.memory_writing.sqlite_store import SQLiteMemoryWriteProposalStore
from cauco_core.memory_writing.store import MemoryWriteProposalStore

NOW = datetime(2026, 8, 5, 8, 0, tzinfo=UTC)
CID = "memory_candidate_" + "a" * 64


def candidate_store() -> MemoryCandidateStore:
    return MemoryCandidateStore(clock=lambda: NOW)


def add_candidate(
    store,
    *,
    cid=CID,
    confidence=0.8,
    category=LessonCategory.EXECUTION,
    tool_id="filesystem",
    operation_id="write_text",
    lesson="Validate the file before writing",
):
    return store.create(
        candidate_id=cid,
        experience_id="experience_abcdefghijklmnopqrstuvwx",
        verification_id="verify_abcdefghijklmnopqrstuvwx",
        execution_id="exec_abcdefghijklmnopqrstuvwx",
        review_id="planrev_abcdefghijklmnopqrstuvwx",
        snapshot_digest="b" * 64,
        lesson=MemoryCandidateLesson(
            category, "The file had to be checked first", lesson, confidence, tool_id, operation_id
        ),
        rationale="Reusable test lesson",
        method="test",
    )


def applied_pair(tmp_path: Path, *, candidate_store=None, candidate_id=CID, **kwargs):
    candidates = candidate_store or candidate_store_fn()
    candidate = add_candidate(candidates, cid=candidate_id, **kwargs)
    candidates.approve(candidate.candidate_id)
    brain = tmp_path / "brain"
    brain.mkdir(parents=True, exist_ok=True)
    (brain / "memory.md").write_text("# Memory\n", encoding="utf-8")
    builder = MemoryWriteProposalBuilder(MemoryEngine(brain), clock=lambda: NOW)
    proposals = MemoryWriteProposalStore(clock=lambda: NOW)
    proposal = builder.build_from_memory_candidate(candidates.get(candidate.candidate_id))
    stored = proposals.put(proposal)
    applied = proposals.mark_applied(stored.proposal.proposal_id, NOW + timedelta(minutes=1))
    return candidates, proposals, applied


def candidate_store_fn():
    return candidate_store()


def test_model_is_frozen_and_validates_fields():
    item = LearningGuidance(
        "c", "e", "p", "planning", "lesson", 0.5, None, None, 1, "why", "source", NOW
    )
    payload = {
        "candidate_id": item.candidate_id,
        "experience_id": item.experience_id,
        "proposal_id": item.proposal_id,
        "category": item.category,
        "lesson": item.lesson,
        "confidence": item.confidence,
        "tool_id": item.tool_id,
        "operation_id": item.operation_id,
        "step_index": item.step_index,
        "reason_selected": item.reason_selected,
        "source_reference": item.source_reference,
        "applied_at": item.applied_at,
    }
    with pytest.raises((AttributeError, TypeError)):
        item.lesson = "changed"  # type: ignore[misc]
    for field in (
        "candidate_id",
        "experience_id",
        "proposal_id",
        "category",
        "lesson",
        "reason_selected",
        "source_reference",
    ):
        with pytest.raises(ValueError):
            LearningGuidance(**{**payload, field: " "})
    with pytest.raises(ValueError):
        LearningGuidance(
            "c", "e", "p", "planning", "lesson", 1.1, None, None, None, "why", "source", NOW
        )
    with pytest.raises(ValueError):
        LearningGuidance(
            "c", "e", "p", "planning", "lesson", 0.5, None, None, 0, "why", "source", NOW
        )
    with pytest.raises(ValueError):
        LearningGuidance(
            "c",
            "e",
            "p",
            "planning",
            "lesson",
            0.5,
            None,
            None,
            None,
            "why",
            "source",
            datetime(2026, 1, 1),
        )


def test_resolver_requires_applied_approved_learning_candidate(tmp_path):
    candidates, proposals, applied = applied_pair(tmp_path)
    result = LearningGuidanceResolver(candidates, proposals).resolve("write the file")
    assert result[0].proposal_id == applied.proposal.proposal_id
    assert result[0].candidate_id == CID
    assert LearningGuidanceResolver(candidates, proposals).resolve("unrelated request") == ()


def test_pending_proposal_is_excluded_and_list_is_bounded(tmp_path):
    candidates = candidate_store()
    candidate = add_candidate(candidates)
    candidates.approve(candidate.candidate_id)
    brain = tmp_path / "brain"
    brain.mkdir(parents=True)
    (brain / "memory.md").write_text("# Memory\n")
    proposal = MemoryWriteProposalBuilder(
        MemoryEngine(brain), clock=lambda: NOW
    ).build_from_memory_candidate(candidates.get(candidate.candidate_id))
    proposals = MemoryWriteProposalStore(clock=lambda: NOW)
    created = proposals.put(proposal)
    assert proposals.list(state=MemoryWriteProposalState.APPLIED) == ()
    assert LearningGuidanceResolver(candidates, proposals).resolve("validate file") == ()
    with pytest.raises(ValueError):
        proposals.list(limit=0)
    with pytest.raises(ValueError):
        LearningGuidanceResolver(candidates, proposals).resolve("x", limit=11)
    snapshot = proposals.list(limit=1)[0]
    snapshot.proposal.reasoning.append("mutated")
    assert proposals.get(created.proposal.proposal_id).proposal.reasoning == proposal.reasoning


def test_exact_tool_operation_and_tie_breaking_are_deterministic(tmp_path):
    candidates = candidate_store()
    proposals = MemoryWriteProposalStore(clock=lambda: NOW)
    brain = tmp_path / "brain"
    brain.mkdir()
    (brain / "memory.md").write_text("# Memory\n", encoding="utf-8")
    builder = MemoryWriteProposalBuilder(MemoryEngine(brain), clock=lambda: NOW)

    def apply(index, **kwargs):
        cid = "memory_candidate_" + chr(97 + index) * 64
        applied_at = kwargs.pop("applied_at")
        candidate = add_candidate(candidates, cid=cid, **kwargs)
        candidate = candidates.approve(cid)
        proposal = proposals.put(builder.build_from_memory_candidate(candidate))
        proposals.mark_applied(proposal.proposal.proposal_id, applied_at)

    apply(0, confidence=0.5, tool_id="other", operation_id="other", applied_at=NOW)
    apply(1, confidence=0.9, tool_id="filesystem", operation_id="other", applied_at=NOW)
    apply(2, confidence=0.7, tool_id="filesystem", operation_id="write_text", applied_at=NOW)
    apply(
        3,
        confidence=0.9,
        tool_id="filesystem",
        operation_id="write_text",
        applied_at=NOW + timedelta(minutes=1),
    )
    apply(
        4,
        confidence=0.9,
        tool_id="filesystem",
        operation_id="write_text",
        applied_at=NOW + timedelta(minutes=1),
    )
    apply(
        5,
        confidence=0.9,
        tool_id="filesystem",
        operation_id="write_text",
        applied_at=NOW + timedelta(minutes=1),
    )

    result = LearningGuidanceResolver(candidates, proposals).resolve(
        "write the file", tool_id="filesystem", operation_id="write_text", limit=10
    )
    assert [item.candidate_id for item in result] == [
        "memory_candidate_" + value * 64 for value in "defcba"
    ]


def test_sqlite_applied_proposal_survives_restart(tmp_path):
    _candidates, _memory, applied = applied_pair(tmp_path)
    database = __import__("cauco_core.persistence", fromlist=["SQLiteDatabase"]).SQLiteDatabase(
        tmp_path / "db.sqlite"
    )
    store = SQLiteMemoryWriteProposalStore(database, clock=lambda: NOW)
    stored = store.put(applied.proposal)
    store.mark_applied(stored.proposal.proposal_id, NOW + timedelta(minutes=1))
    restored = SQLiteMemoryWriteProposalStore(database, clock=lambda: NOW)
    assert (
        restored.list(state=MemoryWriteProposalState.APPLIED)[0].proposal.proposal_id
        == applied.proposal.proposal_id
    )


def test_endpoint_returns_explicit_empty_shape(tmp_path):
    app = __import__("cauco_core.main", fromlist=["create_app"]).create_app(
        Settings(brain_dir=tmp_path / "brain", database_path=tmp_path / "db.sqlite")
    )
    with TestClient(app) as client:
        response = client.get("/api/learning-guidance", params={"instruction": "plan safely"})
    assert response.status_code == 200
    body = response.json()
    assert body["guidance"] == [] and body["count"] == 0
    assert body["method"] == "deterministic_applied_learning_guidance_v1"
    assert body["limitations"]
