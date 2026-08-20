from dataclasses import dataclass
from enum import StrEnum
from threading import Lock, RLock

from cauco_core.agents.review_store import PlanReviewIntegrityError
from cauco_core.execution.models import (
    AgentPlanExecutionRecord,
    ExecutionConflictError,
    ExecutionForbiddenError,
    ExecutionStatus,
    ExecutionValidationError,
    StepExecutionStatus,
)
from cauco_core.execution.recovery import RecoveryContext, RecoveryDecision, RecoveryPolicy
from cauco_core.execution.service import ExecutionService
from cauco_core.execution.store import ExecutionStore
from cauco_core.mutations.models import (
    MutationCapacityError,
    MutationConflictError,
    MutationForbiddenError,
    MutationNotFoundError,
    MutationPreviewStatus,
    MutationValidationError,
)
from cauco_core.mutations.service import MutationService


class TaskRuntimeState(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    AWAITING_CONFIRMATION = "awaiting_confirmation"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    REPLAN_REQUIRED = "replan_required"


@dataclass(frozen=True, slots=True)
class TaskRuntimeStatus:
    execution_id: str
    state: TaskRuntimeState
    current_step_index: int | None
    preview_id: str | None = None
    preview_status: str | None = None
    recovery_decision: RecoveryDecision | None = None


class TaskRuntime:
    """Coordinates approved steps through the existing execution and mutation services."""

    def __init__(
        self,
        execution_service: ExecutionService,
        mutation_service: MutationService,
        execution_store: ExecutionStore,
        recovery_policy: RecoveryPolicy | None = None,
    ) -> None:
        self.execution_service = execution_service
        self.mutation_service = mutation_service
        self.execution_store = execution_store
        self.recovery_policy = recovery_policy or RecoveryPolicy()
        self._locks: dict[str, Lock] = {}
        self._locks_guard = RLock()

    def run(self, execution_id: str) -> TaskRuntimeStatus:
        return self._advance(execution_id, "runtime_started")

    def resume(self, execution_id: str) -> TaskRuntimeStatus:
        return self._advance(execution_id, "runtime_resumed")

    def cancel(self, execution_id: str) -> TaskRuntimeStatus:
        with self._lock(execution_id):
            record = self.execution_store.get(execution_id)
            if any(step.status is StepExecutionStatus.RUNNING for step in record.step_records):
                raise ExecutionConflictError("A running step cannot be interrupted.")
            pending = self._next_pending(record)
            if pending is not None:
                try:
                    preview = self.mutation_service.preview_store.active(
                        execution_id, pending.step_index
                    )
                except MutationNotFoundError:
                    preview = None
                if (
                    preview is not None
                    and preview.status is MutationPreviewStatus.PENDING_CONFIRMATION
                ):
                    try:
                        self.mutation_service.cancel_preview(execution_id, pending.step_index)
                    except (
                        MutationConflictError,
                        MutationForbiddenError,
                        MutationNotFoundError,
                        MutationValidationError,
                    ) as error:
                        raise ExecutionConflictError(
                            "Mutation preview cancellation failed safely."
                        ) from error
            self.execution_service.cancel(execution_id)
            return self.status(execution_id)

    def status(self, execution_id: str) -> TaskRuntimeStatus:
        record = self.execution_store.get(execution_id)
        if record.status is ExecutionStatus.CANCELLED:
            return self._status(record, TaskRuntimeState.CANCELLED)
        if record.status is ExecutionStatus.COMPLETED:
            return self._status(record, TaskRuntimeState.COMPLETED)
        if record.status is ExecutionStatus.FAILED:
            replan = any(
                event.event_type == "recovery_replan_required" for event in record.audit_events
            )
            return self._status(
                record,
                TaskRuntimeState.REPLAN_REQUIRED if replan else TaskRuntimeState.FAILED,
            )
        pending = self._next_pending(record)
        if pending is not None:
            try:
                preview = self.mutation_service.preview_store.active(
                    execution_id, pending.step_index
                )
            except MutationNotFoundError:
                preview = None
            if preview is not None and preview.status is MutationPreviewStatus.PENDING_CONFIRMATION:
                return self._status(
                    record,
                    TaskRuntimeState.AWAITING_CONFIRMATION,
                    step_index=pending.step_index,
                    preview_id=preview.preview_id,
                    preview_status=preview.status.value,
                )
        state = (
            TaskRuntimeState.PENDING
            if record.status is ExecutionStatus.PENDING_EXECUTION
            else TaskRuntimeState.RUNNING
        )
        return self._status(record, state)

    def _advance(self, execution_id: str, event_type: str) -> TaskRuntimeStatus:
        with self._lock(execution_id):
            initial = self.execution_store.get(execution_id)
            if initial.status in {
                ExecutionStatus.COMPLETED,
                ExecutionStatus.FAILED,
                ExecutionStatus.CANCELLED,
            }:
                return self.status(execution_id)
            self.execution_store.append_event(
                execution_id, event_type, "accepted", "Runtime advancement started."
            )
            while True:
                record = self.execution_store.get(execution_id)
                pending = self._next_pending(record)
                if pending is None:
                    if record.status is ExecutionStatus.COMPLETED:
                        self._append_once(
                            record, "runtime_completed", "success", "Runtime completed."
                        )
                    return self.status(execution_id)
                validation = self.execution_service.tool_registry.validate(
                    pending.tool_id, pending.operation_id
                )
                if not validation.valid or not validation.runtime_execution_allowed:
                    return self._stop(
                        record,
                        pending.step_index,
                        RecoveryDecision.ABORT,
                        "forbidden",
                    )
                if validation.preview_required:
                    preview_created = False
                    try:
                        preview = self.mutation_service.preview_store.active(
                            execution_id, pending.step_index
                        )
                    except MutationNotFoundError:
                        preview = None
                    if (
                        preview is None
                        or preview.status is not MutationPreviewStatus.PENDING_CONFIRMATION
                    ):
                        try:
                            preview = self.mutation_service.create_preview(
                                execution_id, pending.step_index
                            )
                            preview_created = True
                        except MutationCapacityError:
                            return self._stop(
                                record,
                                pending.step_index,
                                RecoveryDecision.ABORT,
                                "preview_capacity",
                            )
                        except MutationForbiddenError:
                            return self._stop(
                                record, pending.step_index, RecoveryDecision.ABORT, "forbidden"
                            )
                        except MutationValidationError:
                            return self._stop(
                                record,
                                pending.step_index,
                                RecoveryDecision.ABORT,
                                "preview_validation",
                            )
                        except MutationNotFoundError:
                            return self._stop(
                                record,
                                pending.step_index,
                                RecoveryDecision.ABORT,
                                "preview_not_found",
                            )
                        except MutationConflictError as error:
                            return self._stop(
                                record,
                                pending.step_index,
                                self._preview_conflict_decision(error),
                                self._preview_conflict_code(error),
                            )
                    if preview_created:
                        self.execution_store.append_event(
                            execution_id,
                            "awaiting_confirmation",
                            "paused",
                            "Mutation preview awaits separate human confirmation.",
                            step_index=pending.step_index,
                            tool_id=pending.tool_id,
                            operation_id=pending.operation_id,
                        )
                    return self._status(
                        self.execution_store.get(execution_id),
                        TaskRuntimeState.AWAITING_CONFIRMATION,
                        step_index=pending.step_index,
                        preview_id=preview.preview_id,
                        preview_status=preview.status.value,
                    )
                try:
                    updated = self.execution_service.execute_step(
                        execution_id, pending.step_index
                    )
                except PlanReviewIntegrityError:
                    return self._stop(
                        record,
                        pending.step_index,
                        RecoveryDecision.ABORT,
                        "integrity_failure",
                    )
                except ExecutionForbiddenError:
                    return self._stop(
                        record, pending.step_index, RecoveryDecision.ABORT, "forbidden"
                    )
                except ExecutionValidationError:
                    return self._stop(
                        record,
                        pending.step_index,
                        RecoveryDecision.ABORT,
                        "execution_validation",
                    )
                except ExecutionConflictError as error:
                    return self._stop(
                        record,
                        pending.step_index,
                        RecoveryDecision.ABORT,
                        self._execution_conflict_code(error),
                    )
                failed = next(
                    item for item in updated.step_records if item.step_index == pending.step_index
                )
                if failed.status is not StepExecutionStatus.FAILED:
                    continue
                result = failed.result
                decision = self.recovery_policy.evaluate(
                    RecoveryContext(
                        tool_id=failed.tool_id,
                        operation_id=failed.operation_id,
                        error_code=result.error_code if result and result.error_code else "unknown",
                        execution_performed=failed.execution_performed,
                        mutation_performed=bool(result and result.mutation_performed),
                        attempt_count=self._attempt_count(updated, failed.step_index),
                    )
                )
                if decision is RecoveryDecision.RETRY:
                    self.execution_store.retry_step(execution_id, failed.step_index)
                    self.execution_store.append_event(
                        execution_id,
                        "recovery_retry",
                        "accepted",
                        "A bounded safe retry was approved.",
                        step_index=failed.step_index,
                        tool_id=failed.tool_id,
                        operation_id=failed.operation_id,
                    )
                    continue
                if decision is RecoveryDecision.SKIP:
                    self.execution_store.skip_failed_step(execution_id, failed.step_index)
                    self.execution_store.append_event(
                        execution_id,
                        "recovery_skip",
                        "accepted",
                        "Recovery skipped the failed optional step.",
                        step_index=failed.step_index,
                        tool_id=failed.tool_id,
                        operation_id=failed.operation_id,
                    )
                    continue
                return self._stop(
                    updated,
                    failed.step_index,
                    decision,
                    result.error_code if result and result.error_code else "unknown",
                    already_failed=True,
                )

    def _stop(
        self,
        record: AgentPlanExecutionRecord,
        step_index: int,
        decision: RecoveryDecision,
        error_code: str,
        *,
        already_failed: bool = False,
    ) -> TaskRuntimeStatus:
        event_type = (
            "recovery_replan_required"
            if decision is RecoveryDecision.REPLAN_REQUIRED
            else "recovery_abort"
        )
        if not already_failed:
            self.execution_store.fail_runtime(
                record.execution_id, "Runtime stopped safely after a blocking failure."
            )
        self.execution_store.append_event(
            record.execution_id,
            event_type,
            error_code,
            "Runtime requires a new reviewed plan."
            if decision is RecoveryDecision.REPLAN_REQUIRED
            else "Runtime aborted safely.",
            step_index=step_index,
        )
        state = (
            TaskRuntimeState.REPLAN_REQUIRED
            if decision is RecoveryDecision.REPLAN_REQUIRED
            else TaskRuntimeState.FAILED
        )
        return self._status(
            self.execution_store.get(record.execution_id), state, recovery_decision=decision
        )

    def _lock(self, execution_id: str) -> Lock:
        with self._locks_guard:
            return self._locks.setdefault(execution_id, Lock())

    @staticmethod
    def _execution_conflict_code(error: ExecutionConflictError) -> str:
        if str(error) == "Snapshot digest verification failed.":
            return "snapshot_mismatch"
        return "execution_conflict"

    @staticmethod
    def _preview_conflict_decision(error: MutationConflictError) -> RecoveryDecision:
        operational_drift = {
            "A local commit requires staged changes.",
            "Git state changed after commit preview creation.",
            "Local or remote push state changed after preview creation.",
            "Persistent state changed after preview creation.",
            "The current branch does not match the approved push branch.",
            "The create-only target already exists.",
            "The local branch tip does not match the approved commit.",
            "The remote branch no longer matches the approved remote state.",
            "The replacement target does not exist.",
            "The staged paths do not match the approved commit step.",
        }
        return (
            RecoveryDecision.REPLAN_REQUIRED
            if str(error) in operational_drift
            else RecoveryDecision.ABORT
        )

    @classmethod
    def _preview_conflict_code(cls, error: MutationConflictError) -> str:
        return (
            "stale_state"
            if cls._preview_conflict_decision(error) is RecoveryDecision.REPLAN_REQUIRED
            else "preview_conflict"
        )

    @staticmethod
    def _next_pending(record: AgentPlanExecutionRecord):
        return next(
            (
                step
                for step in sorted(record.step_records, key=lambda item: item.step_index)
                if step.status is StepExecutionStatus.PENDING
            ),
            None,
        )

    @staticmethod
    def _attempt_count(record: AgentPlanExecutionRecord, step_index: int) -> int:
        return sum(
            event.event_type == "step_started" and event.step_index == step_index
            for event in record.audit_events
        )

    def _append_once(
        self, record: AgentPlanExecutionRecord, event_type: str, outcome: str, message: str
    ) -> None:
        if not any(event.event_type == event_type for event in record.audit_events):
            self.execution_store.append_event(record.execution_id, event_type, outcome, message)

    @staticmethod
    def _status(
        record: AgentPlanExecutionRecord,
        state: TaskRuntimeState,
        *,
        step_index: int | None = None,
        preview_id: str | None = None,
        preview_status: str | None = None,
        recovery_decision: RecoveryDecision | None = None,
    ) -> TaskRuntimeStatus:
        return TaskRuntimeStatus(
            execution_id=record.execution_id,
            state=state,
            current_step_index=(
                step_index if step_index is not None else record.current_step_index
            ),
            preview_id=preview_id,
            preview_status=preview_status,
            recovery_decision=recovery_decision,
        )
