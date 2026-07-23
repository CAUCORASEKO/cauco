import pytest
from cauco_agents import AgentPlanReviewStatus

from cauco_core.execution.models import ExecutionStatus
from cauco_core.executive import (
    ExecutiveAction,
    ExecutiveControlService,
    ExecutiveState,
    IntentStatus,
)


def decide(**changes):
    values = {
        "intent_status": IntentStatus.CLEAR,
        "perception_available": True,
        "plan_available": True,
    }
    values.update(changes)
    return ExecutiveControlService().decide(ExecutiveState(**values))


@pytest.mark.parametrize(
    ("intent_status", "expected"),
    [
        (IntentStatus.UNKNOWN, ExecutiveAction.CLARIFY_INTENT),
        (IntentStatus.AMBIGUOUS, ExecutiveAction.CLARIFY_INTENT),
    ],
)
def test_unclear_intent_requires_clarification(
    intent_status: IntentStatus,
    expected: ExecutiveAction,
) -> None:
    decision = ExecutiveControlService().decide(ExecutiveState(intent_status=intent_status))

    assert decision.next_action is expected
    assert decision.requires_human_approval is False
    assert decision.transition_permitted is True


def test_clear_intent_observes_before_planning() -> None:
    decision = ExecutiveControlService().decide(ExecutiveState(intent_status=IntentStatus.CLEAR))

    assert decision.next_action is ExecutiveAction.OBSERVE


def test_observed_state_progresses_to_plan_preparation() -> None:
    decision = ExecutiveControlService().decide(
        ExecutiveState(
            intent_status=IntentStatus.CLEAR,
            perception_available=True,
        )
    )

    assert decision.next_action is ExecutiveAction.PREPARE_PLAN


def test_available_plan_requests_human_review() -> None:
    decision = decide()

    assert decision.next_action is ExecutiveAction.REQUEST_PLAN_REVIEW
    assert decision.requires_human_approval is True


def test_pending_review_blocks_progression() -> None:
    decision = decide(review_status=AgentPlanReviewStatus.PENDING_REVIEW)

    assert decision.next_action is ExecutiveAction.AWAIT_HUMAN_DECISION
    assert decision.transition_permitted is False
    assert decision.requires_human_approval is True


@pytest.mark.parametrize(
    "status",
    [
        AgentPlanReviewStatus.REJECTED,
        AgentPlanReviewStatus.CANCELLED,
        AgentPlanReviewStatus.EXPIRED,
    ],
)
def test_terminal_nonapproved_review_stops(status: AgentPlanReviewStatus) -> None:
    decision = decide(review_status=status)

    assert decision.next_action is ExecutiveAction.STOP
    assert decision.transition_permitted is False


def test_approved_review_allows_only_execution_record_creation() -> None:
    decision = decide(review_status=AgentPlanReviewStatus.APPROVED)

    assert decision.next_action is ExecutiveAction.CREATE_EXECUTION_RECORD
    assert decision.requires_human_approval is True
    assert decision.transition_permitted is True


def test_pending_execution_requests_separate_step_approval() -> None:
    decision = decide(
        review_status=AgentPlanReviewStatus.APPROVED,
        execution_record_available=True,
        execution_status=ExecutionStatus.PENDING_EXECUTION,
    )

    assert decision.next_action is ExecutiveAction.REQUEST_STEP_APPROVAL
    assert decision.requires_human_approval is True


def test_running_execution_blocks_concurrent_progression() -> None:
    decision = decide(
        review_status=AgentPlanReviewStatus.APPROVED,
        execution_record_available=True,
        execution_status=ExecutionStatus.RUNNING,
    )

    assert decision.next_action is ExecutiveAction.STOP
    assert decision.transition_permitted is False


def test_completed_execution_requires_verification() -> None:
    decision = decide(
        review_status=AgentPlanReviewStatus.APPROVED,
        execution_record_available=True,
        execution_status=ExecutionStatus.COMPLETED,
        execution_performed=True,
    )

    assert decision.next_action is ExecutiveAction.VERIFY_OUTCOME
    assert decision.requires_human_approval is False


def test_verified_success_completes_workflow() -> None:
    decision = decide(
        review_status=AgentPlanReviewStatus.APPROVED,
        execution_record_available=True,
        execution_status=ExecutionStatus.COMPLETED,
        execution_performed=True,
        outcome_verified=True,
        verification_succeeded=True,
    )

    assert decision.next_action is ExecutiveAction.COMPLETE
    assert decision.transition_permitted is True


def test_failed_verification_stops_and_requires_new_decision() -> None:
    decision = decide(
        review_status=AgentPlanReviewStatus.APPROVED,
        execution_record_available=True,
        execution_status=ExecutionStatus.COMPLETED,
        execution_performed=True,
        outcome_verified=True,
        verification_succeeded=False,
    )

    assert decision.next_action is ExecutiveAction.STOP
    assert decision.transition_permitted is False


def test_failed_attempt_requires_verification_when_operation_ran() -> None:
    decision = decide(
        review_status=AgentPlanReviewStatus.APPROVED,
        execution_record_available=True,
        execution_status=ExecutionStatus.FAILED,
        execution_performed=True,
    )

    assert decision.next_action is ExecutiveAction.VERIFY_OUTCOME


def test_review_requires_plan() -> None:
    with pytest.raises(ValueError, match="requires an available plan"):
        ExecutiveState(
            intent_status=IntentStatus.CLEAR,
            review_status=AgentPlanReviewStatus.PENDING_REVIEW,
        )


def test_execution_record_requires_approved_review() -> None:
    with pytest.raises(ValueError, match="approved review"):
        ExecutiveState(
            intent_status=IntentStatus.CLEAR,
            perception_available=True,
            plan_available=True,
            execution_record_available=True,
        )


def test_execution_status_requires_record() -> None:
    with pytest.raises(ValueError, match="requires an execution record"):
        ExecutiveState(
            intent_status=IntentStatus.CLEAR,
            perception_available=True,
            plan_available=True,
            review_status=AgentPlanReviewStatus.APPROVED,
            execution_status=ExecutionStatus.PENDING_EXECUTION,
        )


def test_verification_requires_performed_execution() -> None:
    with pytest.raises(ValueError, match="requires performed execution"):
        ExecutiveState(
            intent_status=IntentStatus.CLEAR,
            perception_available=True,
            plan_available=True,
            review_status=AgentPlanReviewStatus.APPROVED,
            execution_record_available=True,
            outcome_verified=True,
        )
