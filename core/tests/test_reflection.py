from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from cauco_core.config import Settings
from cauco_core.learning.models import LessonCategory
from cauco_core.main import create_app
from cauco_core.memory.engine import MemoryEngine
from cauco_core.memory_candidates.store import MemoryCandidateStore
from cauco_core.memory_writing.proposal_builder import MemoryWriteProposalBuilder
from cauco_core.memory_writing.store import MemoryWriteProposalStore
from cauco_core.reflection.models import ReflectionPattern, ReflectionSummary
from cauco_core.reflection.resolver import ReflectionResolver

NOW = datetime(2026, 8, 5, 8, 0, tzinfo=UTC)


def _stores(tmp_path: Path):
    candidates = MemoryCandidateStore(clock=lambda: NOW)
    proposals = MemoryWriteProposalStore(clock=lambda: NOW)
    brain = tmp_path / "brain"
    brain.mkdir()
    (brain / "memory.md").write_text("# Memory\n", encoding="utf-8")
    return candidates, proposals, MemoryWriteProposalBuilder(MemoryEngine(brain), clock=lambda: NOW)


def _apply(candidates, proposals, builder, index: int, category: LessonCategory, lesson: str):
    candidate = candidates.create(
        candidate_id="memory_candidate_" + chr(97 + index) * 64,
        experience_id="experience_abcdefghijklmnopqrstuvwx",
        verification_id="verify_abcdefghijklmnopqrstuvwx",
        execution_id="exec_abcdefghijklmnopqrstuvwx",
        review_id="planrev_abcdefghijklmnopqrstuvwx",
        snapshot_digest="a" * 64,
        lesson=__import__(
            "cauco_core.memory_candidates.models", fromlist=["MemoryCandidateLesson"]
        ).MemoryCandidateLesson(category, "Observed", lesson, 0.8),
        rationale="test",
        method="test",
    )
    candidate = candidates.approve(candidate.candidate_id)
    stored = proposals.put(builder.build_from_memory_candidate(candidate))
    proposals.mark_applied(stored.proposal.proposal_id, NOW + timedelta(minutes=index))


def test_empty_reflection_is_immutable_and_deterministic(tmp_path: Path) -> None:
    candidates, proposals, _ = _stores(tmp_path)
    report = ReflectionResolver(candidates, proposals).resolve()
    assert report.summary == ReflectionSummary(0, 0, 0, 0, 0)
    assert report.patterns == ()
    with pytest.raises((AttributeError, TypeError)):
        report.patterns = ()  # type: ignore[misc]
    with pytest.raises((AttributeError, TypeError)):
        ReflectionPattern("planning", "lesson", 1).count = 2  # type: ignore[misc]


def test_reflection_aggregates_repeated_lessons_and_categories(tmp_path: Path) -> None:
    candidates, proposals, builder = _stores(tmp_path)
    _apply(candidates, proposals, builder, 0, LessonCategory.EXECUTION, "Check the file")
    _apply(candidates, proposals, builder, 1, LessonCategory.EXECUTION, "Check the file")
    _apply(candidates, proposals, builder, 2, LessonCategory.PLANNING, "Plan the scope")

    report = ReflectionResolver(candidates, proposals).resolve()
    assert report.summary.approved_candidates == 3
    assert report.summary.applied_learning_proposals == 3
    assert report.summary.execution == 2
    assert report.summary.planning == 1
    assert report.patterns[0] == ReflectionPattern("execution", "Check the file", 2)
    assert report.patterns[1] == ReflectionPattern("planning", "Plan the scope", 1)


def test_reflection_endpoint_returns_stable_json_shape(tmp_path: Path) -> None:
    app = create_app(Settings(brain_dir=tmp_path / "brain", database_path=tmp_path / "db.sqlite"))
    with TestClient(app) as client:
        response = client.get("/api/reflection")
    assert response.status_code == 200
    assert response.json() == {
        "summary": {
            "approved_candidates": 0,
            "applied_learning_proposals": 0,
            "planning": 0,
            "execution": 0,
            "verification": 0,
        },
        "patterns": [],
        "method": "deterministic_applied_learning_reflection_v1",
        "limitations": [
            "Deterministic persisted approved candidates and applied learning proposals "
            "only; no mutation or model inference.",
            "Results are bounded to 100 candidates, proposals, and 20 patterns.",
        ],
    }
