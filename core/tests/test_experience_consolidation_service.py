from datetime import UTC, datetime

import pytest

from cauco_core.learning.models import (
    ExperienceConflictError,
    ExperienceOutcome,
    LessonCategory,
)
from cauco_core.learning.service import ExperienceConsolidationService
from cauco_core.learning.store import ExperienceStore
from cauco_core.verification.models import (
    StepVerificationResult,
    VerificationOutcome,
    VerificationRecommendation,
)
from cauco_core.verification.store import VerificationStore

NOW = datetime(2026, 7, 24, 8, 0, tzinfo=UTC)


def create_verification(
    *,
    outcome: VerificationOutcome,
    step_results: tuple[StepVerificationResult, ...],
) -> tuple[VerificationStore, str]:
    store = VerificationStore(clock=lambda: NOW)

    recommendation = {
        VerificationOutcome.SUCCEEDED: VerificationRecommendation.COMPLETE,
        VerificationOutcome.INSUFFICIENT_EVIDENCE: (VerificationRecommendation.REQUEST_REVIEW),
        VerificationOutcome.PARTIAL_SUCCESS: VerificationRecommendation.STOP,
        VerificationOutcome.FAILED: VerificationRecommendation.STOP,
    }[outcome]

    record = store.create(
        execution_id="exec_" + "e" * 24,
        review_id="review-1",
        snapshot_digest="a" * 64,
        outcome=outcome,
        recommendation=recommendation,
        method="test-verification",
        step_results=step_results,
    )
    return store, record.verification_id


def service_for(
    verification_store: VerificationStore,
) -> ExperienceConsolidationService:
    return ExperienceConsolidationService(
        verification_store=verification_store,
        experience_store=ExperienceStore(clock=lambda: NOW),
    )


def test_successful_verification_creates_no_memory_candidate():
    verifications, verification_id = create_verification(
        outcome=VerificationOutcome.SUCCEEDED,
        step_results=(
            StepVerificationResult(
                step_index=1,
                tool_id="core.files",
                operation_id="read",
                outcome=VerificationOutcome.SUCCEEDED,
                method="test",
            ),
        ),
    )

    record = service_for(verifications).consolidate(verification_id)

    assert record.outcome is ExperienceOutcome.SUCCESS
    assert record.lesson_candidates == ()
    assert record.memory_candidate is False
    assert record.recommendation == "complete"


def test_insufficient_mutation_evidence_creates_reusable_lesson():
    observation = (
        "A persistent mutation was reported without explicit post-action verification evidence."
    )
    verifications, verification_id = create_verification(
        outcome=VerificationOutcome.INSUFFICIENT_EVIDENCE,
        step_results=(
            StepVerificationResult(
                step_index=1,
                tool_id="core.files",
                operation_id="write",
                outcome=VerificationOutcome.INSUFFICIENT_EVIDENCE,
                method="test",
                unresolved_conditions=(observation,),
            ),
        ),
    )

    record = service_for(verifications).consolidate(verification_id)

    assert record.outcome is ExperienceOutcome.INCONCLUSIVE
    assert record.memory_candidate is True
    assert len(record.lesson_candidates) == 1

    lesson = record.lesson_candidates[0]
    assert lesson.category is LessonCategory.VERIFICATION
    assert lesson.observation == observation
    assert lesson.confidence == 0.95
    assert lesson.tool_id == "core.files"
    assert lesson.operation_id == "write"
    assert lesson.step_index == 1


def test_tool_identity_mismatch_creates_tool_reliability_lesson():
    observation = "Tool result identity does not match the approved step."
    verifications, verification_id = create_verification(
        outcome=VerificationOutcome.FAILED,
        step_results=(
            StepVerificationResult(
                step_index=1,
                tool_id="core.files",
                operation_id="write",
                outcome=VerificationOutcome.FAILED,
                method="test",
                deviations=(observation,),
            ),
        ),
    )

    record = service_for(verifications).consolidate(verification_id)

    assert record.outcome is ExperienceOutcome.FAILURE
    assert record.lesson_candidates[0].category is LessonCategory.TOOL_RELIABILITY
    assert record.lesson_candidates[0].confidence == 0.99


def test_duplicate_identical_lessons_are_suppressed():
    observation = "Post-action verification explicitly failed."
    step = StepVerificationResult(
        step_index=1,
        tool_id="core.files",
        operation_id="write",
        outcome=VerificationOutcome.FAILED,
        method="test",
        deviations=(observation, observation),
    )
    verifications, verification_id = create_verification(
        outcome=VerificationOutcome.FAILED,
        step_results=(step,),
    )

    record = service_for(verifications).consolidate(verification_id)

    assert len(record.lesson_candidates) == 1


def test_duplicate_consolidation_is_rejected():
    verifications, verification_id = create_verification(
        outcome=VerificationOutcome.SUCCEEDED,
        step_results=(
            StepVerificationResult(
                step_index=1,
                tool_id="core.files",
                operation_id="read",
                outcome=VerificationOutcome.SUCCEEDED,
                method="test",
            ),
        ),
    )
    service = service_for(verifications)

    service.consolidate(verification_id)

    with pytest.raises(ExperienceConflictError, match="already exists"):
        service.consolidate(verification_id)
