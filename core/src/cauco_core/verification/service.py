from collections.abc import Mapping
from typing import Any

from cauco_agents import AgentPlanReviewStatus

from cauco_core.agents.review_store import AgentPlanReviewStore
from cauco_core.execution.models import (
    AgentPlanExecutionRecord,
    AgentPlanStepExecutionRecord,
    ExecutionStatus,
)
from cauco_core.execution.store import ExecutionStore
from cauco_core.verification.models import (
    StepVerificationResult,
    VerificationConflictError,
    VerificationOutcome,
    VerificationRecommendation,
    VerificationRecord,
    VerificationValidationError,
)
from cauco_core.verification.store import VerificationStore


class VerificationService:
    """Compare an approved plan with evidence from performed execution.

    Verification is observational only. It does not invoke tools, mutate
    targets, repair outcomes, or retry failed operations.
    """

    METHOD = "approved_plan_execution_evidence_v1"

    def __init__(
        self,
        *,
        review_store: AgentPlanReviewStore,
        execution_store: ExecutionStore,
        verification_store: VerificationStore,
    ) -> None:
        self.review_store = review_store
        self.execution_store = execution_store
        self.verification_store = verification_store

    def verify(self, review_id: str) -> VerificationRecord:
        review = self.review_store.get(review_id)
        self.review_store.verify_integrity(review)

        if review.status is not AgentPlanReviewStatus.APPROVED:
            raise VerificationConflictError("Only approved plan reviews can be verified.")

        executions = self.execution_store.list(
            review_id=review_id,
            limit=1,
        )
        if not executions:
            raise VerificationValidationError("No execution record exists for this review.")

        execution = executions[0]
        self._validate_execution(review.snapshot_digest, execution)

        step_results = tuple(self._verify_step(step) for step in execution.step_records)
        outcome = self._overall_outcome(step_results)
        recommendation = self._recommendation(outcome)

        evidence_references = tuple(
            reference for step in step_results for reference in step.evidence_references
        )
        deviations = tuple(deviation for step in step_results for deviation in step.deviations)
        unresolved_conditions = tuple(
            condition for step in step_results for condition in step.unresolved_conditions
        )

        rollback_values = {
            step.rollback_available for step in step_results if step.rollback_available is not None
        }
        rollback_available = rollback_values.pop() if len(rollback_values) == 1 else None

        return self.verification_store.create(
            execution_id=execution.execution_id,
            review_id=review.review_id,
            snapshot_digest=review.snapshot_digest,
            outcome=outcome,
            recommendation=recommendation,
            method=self.METHOD,
            step_results=step_results,
            evidence_references=evidence_references,
            deviations=deviations,
            unresolved_conditions=unresolved_conditions,
            rollback_available=rollback_available,
        )

    @staticmethod
    def _validate_execution(
        snapshot_digest: str,
        execution: AgentPlanExecutionRecord,
    ) -> None:
        if execution.snapshot_digest != snapshot_digest:
            raise VerificationConflictError(
                "Execution snapshot does not match the approved review."
            )
        if execution.status not in {
            ExecutionStatus.COMPLETED,
            ExecutionStatus.FAILED,
        }:
            raise VerificationConflictError("Only terminal performed executions can be verified.")
        if not execution.execution_performed:
            raise VerificationConflictError("Verification requires a performed execution.")

    def _verify_step(
        self,
        step: AgentPlanStepExecutionRecord,
    ) -> StepVerificationResult:
        identity = f"execution-step:{step.step_index}:{step.tool_id}:{step.operation_id}"

        if not step.execution_performed:
            return StepVerificationResult(
                step_index=step.step_index,
                tool_id=step.tool_id,
                operation_id=step.operation_id,
                outcome=VerificationOutcome.INSUFFICIENT_EVIDENCE,
                method=self.METHOD,
                evidence_references=(identity,),
                unresolved_conditions=("The approved operation was not performed.",),
            )

        result = step.result
        if result is None:
            return StepVerificationResult(
                step_index=step.step_index,
                tool_id=step.tool_id,
                operation_id=step.operation_id,
                outcome=VerificationOutcome.INSUFFICIENT_EVIDENCE,
                method=self.METHOD,
                evidence_references=(identity,),
                unresolved_conditions=("No structured tool result is available.",),
            )

        evidence = (
            identity,
            f"tool-result:{result.tool_id}:{result.operation_id}",
        )

        if result.tool_id != step.tool_id or result.operation_id != step.operation_id:
            return StepVerificationResult(
                step_index=step.step_index,
                tool_id=step.tool_id,
                operation_id=step.operation_id,
                outcome=VerificationOutcome.FAILED,
                method=self.METHOD,
                evidence_references=evidence,
                deviations=("Tool result identity does not match the approved step.",),
            )

        if result.truncated:
            return StepVerificationResult(
                step_index=step.step_index,
                tool_id=step.tool_id,
                operation_id=step.operation_id,
                outcome=VerificationOutcome.INSUFFICIENT_EVIDENCE,
                method=self.METHOD,
                evidence_references=evidence,
                observed_conditions=("The operation produced bounded truncated output.",),
                unresolved_conditions=("Relevant verification output may be unavailable.",),
                rollback_available=self._rollback_available(result.structured_data),
            )

        if not result.success:
            return StepVerificationResult(
                step_index=step.step_index,
                tool_id=step.tool_id,
                operation_id=step.operation_id,
                outcome=VerificationOutcome.FAILED,
                method=self.METHOD,
                evidence_references=evidence,
                observed_conditions=("The adapter reported operation failure.",),
                deviations=(
                    result.error_code or "The operation failed without a usable error code.",
                ),
                rollback_available=self._rollback_available(result.structured_data),
            )

        verification_passed = result.structured_data.get("verification_passed")

        if verification_passed is True:
            return StepVerificationResult(
                step_index=step.step_index,
                tool_id=step.tool_id,
                operation_id=step.operation_id,
                outcome=VerificationOutcome.SUCCEEDED,
                method=self.METHOD,
                evidence_references=evidence,
                observed_conditions=("The adapter reported successful post-action verification.",),
                rollback_available=self._rollback_available(result.structured_data),
            )

        if verification_passed is False:
            return StepVerificationResult(
                step_index=step.step_index,
                tool_id=step.tool_id,
                operation_id=step.operation_id,
                outcome=VerificationOutcome.FAILED,
                method=self.METHOD,
                evidence_references=evidence,
                deviations=("Post-action verification explicitly failed.",),
                rollback_available=self._rollback_available(result.structured_data),
            )

        if result.mutation_performed:
            unresolved = (
                "A persistent mutation was reported without explicit "
                "post-action verification evidence."
            )
        else:
            unresolved = (
                "No explicit success criterion or independent verification evidence is available."
            )

        return StepVerificationResult(
            step_index=step.step_index,
            tool_id=step.tool_id,
            operation_id=step.operation_id,
            outcome=VerificationOutcome.INSUFFICIENT_EVIDENCE,
            method=self.METHOD,
            evidence_references=evidence,
            observed_conditions=("The adapter completed successfully.",),
            unresolved_conditions=(unresolved,),
            rollback_available=self._rollback_available(result.structured_data),
        )

    @staticmethod
    def _rollback_available(
        structured_data: Mapping[str, Any],
    ) -> bool | None:
        value = structured_data.get("rollback_available")
        return value if isinstance(value, bool) else None

    @staticmethod
    def _overall_outcome(
        results: tuple[StepVerificationResult, ...],
    ) -> VerificationOutcome:
        outcomes = {result.outcome for result in results}

        if VerificationOutcome.FAILED in outcomes:
            return VerificationOutcome.FAILED

        if outcomes == {VerificationOutcome.SUCCEEDED}:
            return VerificationOutcome.SUCCEEDED

        if VerificationOutcome.SUCCEEDED in outcomes:
            return VerificationOutcome.PARTIAL_SUCCESS

        return VerificationOutcome.INSUFFICIENT_EVIDENCE

    @staticmethod
    def _recommendation(
        outcome: VerificationOutcome,
    ) -> VerificationRecommendation:
        if outcome is VerificationOutcome.SUCCEEDED:
            return VerificationRecommendation.COMPLETE
        if outcome is VerificationOutcome.INSUFFICIENT_EVIDENCE:
            return VerificationRecommendation.REQUEST_REVIEW
        return VerificationRecommendation.STOP
