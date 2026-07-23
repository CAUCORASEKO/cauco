from dataclasses import dataclass
from enum import StrEnum

from cauco_agents import AgentPlanReviewStatus

from cauco_core.execution.models import ExecutionStatus


class IntentStatus(StrEnum):
    UNKNOWN = "unknown"
    AMBIGUOUS = "ambiguous"
    CLEAR = "clear"


class ExecutiveAction(StrEnum):
    CLARIFY_INTENT = "clarify_intent"
    OBSERVE = "observe"
    PREPARE_PLAN = "prepare_plan"
    REQUEST_PLAN_REVIEW = "request_plan_review"
    AWAIT_HUMAN_DECISION = "await_human_decision"
    CREATE_EXECUTION_RECORD = "create_execution_record"
    REQUEST_STEP_APPROVAL = "request_step_approval"
    VERIFY_OUTCOME = "verify_outcome"
    COMPLETE = "complete"
    STOP = "stop"


@dataclass(frozen=True, slots=True)
class ExecutiveState:
    intent_status: IntentStatus
    perception_available: bool = False
    plan_available: bool = False
    review_status: AgentPlanReviewStatus | None = None
    execution_status: ExecutionStatus | None = None
    execution_record_available: bool = False
    execution_performed: bool = False
    outcome_verified: bool = False
    verification_succeeded: bool | None = None

    def __post_init__(self) -> None:
        if self.review_status is not None and not self.plan_available:
            raise ValueError("Review state requires an available plan.")

        if (
            self.execution_record_available
            and self.review_status is not AgentPlanReviewStatus.APPROVED
        ):
            raise ValueError("Execution records require an approved review.")

        if self.execution_status is not None and not self.execution_record_available:
            raise ValueError("Execution status requires an execution record.")

        if self.execution_performed and not self.execution_record_available:
            raise ValueError("Performed execution requires an execution record.")

        if self.outcome_verified and not self.execution_performed:
            raise ValueError("Outcome verification requires performed execution.")

        if self.verification_succeeded is not None and not self.outcome_verified:
            raise ValueError("Verification result requires completed verification.")


@dataclass(frozen=True, slots=True)
class ExecutiveDecision:
    next_action: ExecutiveAction
    requires_human_approval: bool
    transition_permitted: bool
    reason: str
    blocking_reasons: tuple[str, ...] = ()
