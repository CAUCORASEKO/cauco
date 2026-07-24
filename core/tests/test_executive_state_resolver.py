from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from cauco_agents import AgentPlanReviewStatus

from cauco_core.execution.models import ExecutionStatus
from cauco_core.executive import (
    ExecutiveAction,
    ExecutiveControlService,
    ExecutiveStateResolutionError,
    ExecutiveStateResolver,
    IntentStatus,
)
from cauco_core.verification import (
    VerificationNotFoundError,
    VerificationOutcome,
)

REVIEW_ID = "planrev_test_review_identifier"
EXECUTION_ID = "exec_test_execution_identifier"
SNAPSHOT_DIGEST = "a" * 64


def review(
    status: AgentPlanReviewStatus,
    *,
    snapshot_digest: str = SNAPSHOT_DIGEST,
) -> SimpleNamespace:
    return SimpleNamespace(
        review_id=REVIEW_ID,
        status=status,
        snapshot_digest=snapshot_digest,
    )


def execution(
    status: ExecutionStatus,
    *,
    performed: bool = False,
    review_id: str = REVIEW_ID,
    snapshot_digest: str = SNAPSHOT_DIGEST,
) -> SimpleNamespace:
    return SimpleNamespace(
        execution_id=EXECUTION_ID,
        review_id=review_id,
        snapshot_digest=snapshot_digest,
        status=status,
        execution_performed=performed,
    )


def verification(
    outcome: VerificationOutcome,
    *,
    execution_id: str = EXECUTION_ID,
    review_id: str = REVIEW_ID,
    snapshot_digest: str = SNAPSHOT_DIGEST,
) -> SimpleNamespace:
    return SimpleNamespace(
        execution_id=execution_id,
        review_id=review_id,
        snapshot_digest=snapshot_digest,
        outcome=outcome,
    )


def resolver_for(
    review_record: SimpleNamespace,
    execution_record: SimpleNamespace | None = None,
    verification_record: SimpleNamespace | None = None,
) -> ExecutiveStateResolver:
    review_store = Mock()
    review_store.get.return_value = review_record

    execution_store = Mock()
    execution_store.list.return_value = (execution_record,) if execution_record is not None else ()

    verification_store = Mock()
    if verification_record is None:
        verification_store.for_execution.side_effect = VerificationNotFoundError(
            "Verification record not found."
        )
    else:
        verification_store.for_execution.return_value = verification_record

    return ExecutiveStateResolver(
        review_store,
        execution_store,
        verification_store,
    )


def test_pending_review_is_normalized_without_execution() -> None:
    resolver = resolver_for(review(AgentPlanReviewStatus.PENDING_REVIEW))

    state = resolver.resolve(REVIEW_ID)

    assert state.intent_status is IntentStatus.CLEAR
    assert state.perception_available is True
    assert state.plan_available is True
    assert state.review_status is AgentPlanReviewStatus.PENDING_REVIEW
    assert state.execution_record_available is False
    assert state.execution_status is None
    assert state.execution_performed is False
    assert state.outcome_verified is False
    assert state.verification_succeeded is None


def test_approved_review_without_execution_requests_record_creation() -> None:
    resolver = resolver_for(review(AgentPlanReviewStatus.APPROVED))

    state = resolver.resolve(REVIEW_ID)
    decision = ExecutiveControlService().decide(state)

    assert decision.next_action is ExecutiveAction.CREATE_EXECUTION_RECORD


def test_pending_execution_requests_separate_step_approval() -> None:
    resolver = resolver_for(
        review(AgentPlanReviewStatus.APPROVED),
        execution(ExecutionStatus.PENDING_EXECUTION),
    )

    state = resolver.resolve(REVIEW_ID)
    decision = ExecutiveControlService().decide(state)

    assert state.execution_record_available is True
    assert state.execution_status is ExecutionStatus.PENDING_EXECUTION
    assert decision.next_action is ExecutiveAction.REQUEST_STEP_APPROVAL


def test_completed_execution_requires_outcome_verification() -> None:
    resolver = resolver_for(
        review(AgentPlanReviewStatus.APPROVED),
        execution(ExecutionStatus.COMPLETED, performed=True),
    )

    state = resolver.resolve(REVIEW_ID)
    decision = ExecutiveControlService().decide(state)

    assert state.execution_performed is True
    assert state.outcome_verified is False
    assert state.verification_succeeded is None
    assert decision.next_action is ExecutiveAction.VERIFY_OUTCOME


def test_failed_performed_execution_requires_outcome_verification() -> None:
    resolver = resolver_for(
        review(AgentPlanReviewStatus.APPROVED),
        execution(ExecutionStatus.FAILED, performed=True),
    )

    decision = ExecutiveControlService().decide(resolver.resolve(REVIEW_ID))

    assert decision.next_action is ExecutiveAction.VERIFY_OUTCOME


def test_snapshot_mismatch_is_rejected() -> None:
    resolver = resolver_for(
        review(AgentPlanReviewStatus.APPROVED),
        execution(
            ExecutionStatus.PENDING_EXECUTION,
            snapshot_digest="b" * 64,
        ),
    )

    with pytest.raises(
        ExecutiveStateResolutionError,
        match="snapshot digests do not match",
    ):
        resolver.resolve(REVIEW_ID)


def test_execution_from_another_review_is_rejected() -> None:
    resolver = resolver_for(
        review(AgentPlanReviewStatus.APPROVED),
        execution(
            ExecutionStatus.PENDING_EXECUTION,
            review_id="planrev_other_review_identifier",
        ),
    )

    with pytest.raises(
        ExecutiveStateResolutionError,
        match="does not belong",
    ):
        resolver.resolve(REVIEW_ID)


def test_successful_verification_completes_workflow() -> None:
    resolver = resolver_for(
        review(AgentPlanReviewStatus.APPROVED),
        execution(ExecutionStatus.COMPLETED, performed=True),
        verification(VerificationOutcome.SUCCEEDED),
    )

    state = resolver.resolve(REVIEW_ID)
    decision = ExecutiveControlService().decide(state)

    assert state.outcome_verified is True
    assert state.verification_succeeded is True
    assert decision.next_action is ExecutiveAction.COMPLETE


@pytest.mark.parametrize(
    "outcome",
    [
        VerificationOutcome.FAILED,
        VerificationOutcome.PARTIAL_SUCCESS,
        VerificationOutcome.INSUFFICIENT_EVIDENCE,
    ],
)
def test_non_successful_verification_stops_workflow(
    outcome: VerificationOutcome,
) -> None:
    resolver = resolver_for(
        review(AgentPlanReviewStatus.APPROVED),
        execution(ExecutionStatus.COMPLETED, performed=True),
        verification(outcome),
    )

    state = resolver.resolve(REVIEW_ID)
    decision = ExecutiveControlService().decide(state)

    assert state.outcome_verified is True
    assert state.verification_succeeded is False
    assert decision.next_action is ExecutiveAction.STOP


def test_verification_from_another_execution_is_rejected() -> None:
    resolver = resolver_for(
        review(AgentPlanReviewStatus.APPROVED),
        execution(ExecutionStatus.COMPLETED, performed=True),
        verification(
            VerificationOutcome.SUCCEEDED,
            execution_id="exec_other_execution_identifier",
        ),
    )

    with pytest.raises(
        ExecutiveStateResolutionError,
        match="does not belong to the resolved execution",
    ):
        resolver.resolve(REVIEW_ID)


def test_verification_from_another_review_is_rejected() -> None:
    resolver = resolver_for(
        review(AgentPlanReviewStatus.APPROVED),
        execution(ExecutionStatus.COMPLETED, performed=True),
        verification(
            VerificationOutcome.SUCCEEDED,
            review_id="planrev_other_review_identifier",
        ),
    )

    with pytest.raises(
        ExecutiveStateResolutionError,
        match="does not belong to the requested review",
    ):
        resolver.resolve(REVIEW_ID)


def test_verification_snapshot_mismatch_is_rejected() -> None:
    resolver = resolver_for(
        review(AgentPlanReviewStatus.APPROVED),
        execution(ExecutionStatus.COMPLETED, performed=True),
        verification(
            VerificationOutcome.SUCCEEDED,
            snapshot_digest="b" * 64,
        ),
    )

    with pytest.raises(
        ExecutiveStateResolutionError,
        match="Verification and review snapshot digests do not match",
    ):
        resolver.resolve(REVIEW_ID)
