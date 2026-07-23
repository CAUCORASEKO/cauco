from cauco_agents import AgentPlanReviewStatus

from cauco_core.execution.models import ExecutionStatus
from cauco_core.executive.models import (
    ExecutiveAction,
    ExecutiveDecision,
    ExecutiveState,
    IntentStatus,
)


class ExecutiveControlService:
    """Determine the next permitted cognitive workflow transition.

    This service coordinates workflow state only. It does not approve plans,
    create execution records, invoke tools, or mutate external state.
    """

    def decide(self, state: ExecutiveState) -> ExecutiveDecision:
        if state.intent_status in {IntentStatus.UNKNOWN, IntentStatus.AMBIGUOUS}:
            return ExecutiveDecision(
                next_action=ExecutiveAction.CLARIFY_INTENT,
                requires_human_approval=False,
                transition_permitted=True,
                reason="The human intent is not sufficiently clear.",
            )

        if not state.perception_available:
            return ExecutiveDecision(
                next_action=ExecutiveAction.OBSERVE,
                requires_human_approval=False,
                transition_permitted=True,
                reason="Relevant current state has not yet been observed.",
            )

        if not state.plan_available:
            return ExecutiveDecision(
                next_action=ExecutiveAction.PREPARE_PLAN,
                requires_human_approval=False,
                transition_permitted=True,
                reason="A candidate plan has not yet been prepared.",
            )

        if state.review_status is None:
            return ExecutiveDecision(
                next_action=ExecutiveAction.REQUEST_PLAN_REVIEW,
                requires_human_approval=True,
                transition_permitted=True,
                reason="The candidate plan requires explicit human review.",
            )

        if state.review_status is AgentPlanReviewStatus.PENDING_REVIEW:
            return ExecutiveDecision(
                next_action=ExecutiveAction.AWAIT_HUMAN_DECISION,
                requires_human_approval=True,
                transition_permitted=False,
                reason="The plan is waiting for an explicit human decision.",
                blocking_reasons=("Plan review is still pending.",),
            )

        if state.review_status in {
            AgentPlanReviewStatus.REJECTED,
            AgentPlanReviewStatus.CANCELLED,
            AgentPlanReviewStatus.EXPIRED,
        }:
            return ExecutiveDecision(
                next_action=ExecutiveAction.STOP,
                requires_human_approval=False,
                transition_permitted=False,
                reason=f"The reviewed plan is {state.review_status.value}.",
                blocking_reasons=("A new or revised plan requires a new review snapshot.",),
            )

        if state.review_status is not AgentPlanReviewStatus.APPROVED:
            return ExecutiveDecision(
                next_action=ExecutiveAction.STOP,
                requires_human_approval=False,
                transition_permitted=False,
                reason="The review state is not eligible for progression.",
                blocking_reasons=("Unsupported review state.",),
            )

        if not state.execution_record_available:
            return ExecutiveDecision(
                next_action=ExecutiveAction.CREATE_EXECUTION_RECORD,
                requires_human_approval=True,
                transition_permitted=True,
                reason=("The approved plan may progress to inert execution-record creation only."),
            )

        if state.execution_status is ExecutionStatus.PENDING_EXECUTION:
            return ExecutiveDecision(
                next_action=ExecutiveAction.REQUEST_STEP_APPROVAL,
                requires_human_approval=True,
                transition_permitted=True,
                reason=(
                    "The execution record is inert and the next stored step "
                    "requires separate approval."
                ),
            )

        if state.execution_status is ExecutionStatus.RUNNING:
            return ExecutiveDecision(
                next_action=ExecutiveAction.STOP,
                requires_human_approval=False,
                transition_permitted=False,
                reason="An approved step is currently running.",
                blocking_reasons=("Concurrent progression is not permitted.",),
            )

        if state.execution_status is ExecutionStatus.CANCELLED:
            return ExecutiveDecision(
                next_action=ExecutiveAction.STOP,
                requires_human_approval=False,
                transition_permitted=False,
                reason="The execution was cancelled.",
            )

        if state.execution_status is ExecutionStatus.FAILED:
            if state.execution_performed and not state.outcome_verified:
                return ExecutiveDecision(
                    next_action=ExecutiveAction.VERIFY_OUTCOME,
                    requires_human_approval=False,
                    transition_permitted=True,
                    reason=(
                        "The operation was attempted but failed; the resulting "
                        "state must be verified."
                    ),
                )
            return ExecutiveDecision(
                next_action=ExecutiveAction.STOP,
                requires_human_approval=False,
                transition_permitted=False,
                reason="The execution failed before a verifiable outcome was produced.",
                blocking_reasons=("A new human-reviewed proposal may be required.",),
            )

        if state.execution_status is ExecutionStatus.COMPLETED:
            if not state.execution_performed:
                return ExecutiveDecision(
                    next_action=ExecutiveAction.STOP,
                    requires_human_approval=False,
                    transition_permitted=False,
                    reason="Execution is marked completed without a performed operation.",
                    blocking_reasons=("Execution state is inconsistent.",),
                )

            if not state.outcome_verified:
                return ExecutiveDecision(
                    next_action=ExecutiveAction.VERIFY_OUTCOME,
                    requires_human_approval=False,
                    transition_permitted=True,
                    reason="The performed operation still requires outcome verification.",
                )

            if state.verification_succeeded:
                return ExecutiveDecision(
                    next_action=ExecutiveAction.COMPLETE,
                    requires_human_approval=False,
                    transition_permitted=True,
                    reason="The approved outcome was verified successfully.",
                )

            return ExecutiveDecision(
                next_action=ExecutiveAction.STOP,
                requires_human_approval=False,
                transition_permitted=False,
                reason="Outcome verification did not confirm success.",
                blocking_reasons=("Further action requires a new human decision.",),
            )

        return ExecutiveDecision(
            next_action=ExecutiveAction.STOP,
            requires_human_approval=False,
            transition_permitted=False,
            reason="No safe cognitive transition is available.",
        )
