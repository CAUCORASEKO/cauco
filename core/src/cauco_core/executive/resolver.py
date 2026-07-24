from __future__ import annotations

from cauco_core.agents.review_store import AgentPlanReviewStore
from cauco_core.execution.store import ExecutionStore
from cauco_core.executive.models import ExecutiveState, IntentStatus
from cauco_core.verification import (
    VerificationNotFoundError,
    VerificationOutcome,
    VerificationStore,
)


class ExecutiveStateResolutionError(RuntimeError):
    """Raised when persisted operational state cannot be safely normalized."""


class ExecutiveStateResolver:
    """Compose executive workflow state from persisted operational records.

    The resolver observes and normalizes existing state only. It does not
    approve plans, create executions, invoke tools, or infer outcome
    verification from tool-specific audit events.
    """

    def __init__(
        self,
        review_store: AgentPlanReviewStore,
        execution_store: ExecutionStore,
        verification_store: VerificationStore | None = None,
    ) -> None:
        self.review_store = review_store
        self.execution_store = execution_store
        self.verification_store = verification_store

    def resolve(self, review_id: str) -> ExecutiveState:
        review = self.review_store.get(review_id)
        executions = self.execution_store.list(review_id=review_id, limit=1)
        execution = executions[0] if executions else None

        if execution is not None:
            if execution.review_id != review.review_id:
                raise ExecutiveStateResolutionError(
                    "Execution record does not belong to the requested review."
                )

            if execution.snapshot_digest != review.snapshot_digest:
                raise ExecutiveStateResolutionError(
                    "Execution and review snapshot digests do not match."
                )

        verification = None
        if execution is not None and self.verification_store is not None:
            try:
                verification = self.verification_store.for_execution(execution.execution_id)
            except VerificationNotFoundError:
                verification = None

        if verification is not None:
            if verification.execution_id != execution.execution_id:
                raise ExecutiveStateResolutionError(
                    "Verification record does not belong to the resolved execution."
                )

            if verification.review_id != review.review_id:
                raise ExecutiveStateResolutionError(
                    "Verification record does not belong to the requested review."
                )

            if verification.snapshot_digest != review.snapshot_digest:
                raise ExecutiveStateResolutionError(
                    "Verification and review snapshot digests do not match."
                )

        return ExecutiveState(
            intent_status=IntentStatus.CLEAR,
            perception_available=True,
            plan_available=True,
            review_status=review.status,
            execution_status=execution.status if execution is not None else None,
            execution_record_available=execution is not None,
            execution_performed=(execution.execution_performed if execution is not None else False),
            outcome_verified=verification is not None,
            verification_succeeded=(
                verification.outcome is VerificationOutcome.SUCCEEDED
                if verification is not None
                else None
            ),
        )
