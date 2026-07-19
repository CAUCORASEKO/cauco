import secrets
from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime
from threading import RLock

from cauco_tools import ToolExecutionResult

from cauco_core.execution.models import (
    AgentPlanExecutionRecord,
    AgentPlanStepExecutionRecord,
    ExecutionAuditEvent,
    ExecutionCapacityError,
    ExecutionConflictError,
    ExecutionNotFoundError,
    ExecutionStatus,
    StepExecutionStatus,
)


class ExecutionStore:
    def __init__(
        self,
        *,
        max_records: int = 100,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        if not 1 <= max_records <= 10_000:
            raise ValueError("Execution capacity must be between 1 and 10000.")
        self.max_records = max_records
        self.clock = clock or (lambda: datetime.now(tz=UTC))
        self._records: dict[str, AgentPlanExecutionRecord] = {}
        self._by_review: dict[str, str] = {}
        self._rejected_events: tuple[ExecutionAuditEvent, ...] = ()
        self._lock = RLock()

    def create(
        self,
        review_id: str,
        snapshot_digest: str,
        steps: tuple[AgentPlanStepExecutionRecord, ...],
    ) -> AgentPlanExecutionRecord:
        with self._lock:
            if review_id in self._by_review:
                raise ExecutionConflictError("An execution record already exists for this review.")
            self._make_room()
            execution_id = f"exec_{secrets.token_urlsafe(18)}"
            now = self.clock()
            record = AgentPlanExecutionRecord(
                execution_id=execution_id,
                review_id=review_id,
                snapshot_digest=snapshot_digest,
                status=ExecutionStatus.PENDING_EXECUTION,
                created_at=now,
                started_at=None,
                completed_at=None,
                current_step_index=None,
                total_steps=len(steps),
                step_records=steps,
                execution_performed=False,
                failure_reason=None,
                audit_events=(),
            )
            record = self._with_event(
                record, "execution_created", "accepted", "Execution record created."
            )
            self._records[execution_id] = record
            self._by_review[review_id] = execution_id
            return record

    def get(self, execution_id: str) -> AgentPlanExecutionRecord:
        with self._lock:
            return self._record(execution_id)

    def list(
        self,
        *,
        status: ExecutionStatus | None = None,
        review_id: str | None = None,
        limit: int = 20,
    ) -> tuple[AgentPlanExecutionRecord, ...]:
        if not 1 <= limit <= 100:
            raise ValueError("Execution list limit must be between 1 and 100.")
        with self._lock:
            records = (
                item
                for item in self._records.values()
                if (status is None or item.status is status)
                and (review_id is None or item.review_id == review_id)
            )
            return tuple(
                sorted(
                    records, key=lambda item: (item.created_at, item.execution_id), reverse=True
                )[:limit]
            )

    def append_event(
        self,
        execution_id: str,
        event_type: str,
        outcome: str,
        message: str,
        *,
        step_index: int | None = None,
        tool_id: str | None = None,
        operation_id: str | None = None,
    ) -> AgentPlanExecutionRecord:
        with self._lock:
            record = self._with_event(
                self._record(execution_id),
                event_type,
                outcome,
                message,
                step_index=step_index,
                tool_id=tool_id,
                operation_id=operation_id,
            )
            self._records[execution_id] = record
            return record

    def record_rejected_attempt(self, review_id: str, message: str) -> None:
        with self._lock:
            self._rejected_events = (
                *self._rejected_events[-99:],
                self._event(None, review_id, "execution_rejected", "rejected", message),
            )

    def start_step(self, execution_id: str, step_index: int) -> AgentPlanExecutionRecord:
        with self._lock:
            record = self._record(execution_id)
            if record.status not in {ExecutionStatus.PENDING_EXECUTION, ExecutionStatus.RUNNING}:
                raise ExecutionConflictError(f"Execution is already {record.status.value}.")
            position, step = self._step(record, step_index)
            if step.status is not StepExecutionStatus.PENDING:
                rejected = self._with_event(
                    record,
                    "execution_rejected",
                    "conflict",
                    "Step execution was rejected.",
                    step_index=step_index,
                    tool_id=step.tool_id,
                    operation_id=step.operation_id,
                )
                self._records[execution_id] = rejected
                raise ExecutionConflictError(f"Step is already {step.status.value}.")
            now = self.clock()
            updated_step = replace(step, status=StepExecutionStatus.RUNNING, started_at=now)
            steps = list(record.step_records)
            steps[position] = updated_step
            updated = replace(
                record,
                status=ExecutionStatus.RUNNING,
                started_at=record.started_at or now,
                current_step_index=step_index,
                step_records=tuple(steps),
            )
            updated = self._with_event(
                updated,
                "step_started",
                "accepted",
                "Allowlisted step started.",
                step_index=step_index,
                tool_id=step.tool_id,
                operation_id=step.operation_id,
            )
            self._records[execution_id] = updated
            return updated

    def finish_step(
        self,
        execution_id: str,
        step_index: int,
        *,
        result: ToolExecutionResult | None,
        error: str | None,
        performed: bool,
    ) -> AgentPlanExecutionRecord:
        with self._lock:
            record = self._record(execution_id)
            position, step = self._step(record, step_index)
            if step.status is not StepExecutionStatus.RUNNING:
                raise ExecutionConflictError("Step is not running.")
            now = self.clock()
            successful = result is not None and result.success
            updated_step = replace(
                step,
                status=StepExecutionStatus.COMPLETED if successful else StepExecutionStatus.FAILED,
                completed_at=now,
                result=result,
                error=error,
                execution_performed=performed,
            )
            steps = list(record.step_records)
            steps[position] = updated_step
            terminal = all(
                item.status in {StepExecutionStatus.COMPLETED, StepExecutionStatus.SKIPPED}
                for item in steps
            )
            status = (
                ExecutionStatus.FAILED
                if not successful
                else ExecutionStatus.COMPLETED
                if terminal
                else ExecutionStatus.RUNNING
            )
            updated = replace(
                record,
                status=status,
                completed_at=now
                if status in {ExecutionStatus.COMPLETED, ExecutionStatus.FAILED}
                else None,
                current_step_index=None,
                step_records=tuple(steps),
                execution_performed=record.execution_performed or performed,
                failure_reason=error if status is ExecutionStatus.FAILED else None,
            )
            event_type = "step_completed" if successful else "step_failed"
            updated = self._with_event(
                updated,
                event_type,
                "success" if successful else "failed",
                "Step completed." if successful else "Step failed safely.",
                step_index=step_index,
                tool_id=step.tool_id,
                operation_id=step.operation_id,
            )
            if result is not None and result.truncated:
                updated = self._with_event(
                    updated,
                    "output_truncated",
                    "bounded",
                    "Tool output was truncated.",
                    step_index=step_index,
                    tool_id=step.tool_id,
                    operation_id=step.operation_id,
                )
            if status is ExecutionStatus.COMPLETED:
                updated = self._with_event(
                    updated, "execution_completed", "success", "Execution completed."
                )
            self._records[execution_id] = updated
            return updated

    def fail_before_start(self, execution_id: str, reason: str) -> AgentPlanExecutionRecord:
        with self._lock:
            record = self._record(execution_id)
            now = self.clock()
            updated = replace(
                record, status=ExecutionStatus.FAILED, completed_at=now, failure_reason=reason
            )
            updated = self._with_event(updated, "execution_rejected", "rejected", reason)
            self._records[execution_id] = updated
            return updated

    def cancel(self, execution_id: str) -> AgentPlanExecutionRecord:
        with self._lock:
            record = self._record(execution_id)
            if record.status is not ExecutionStatus.PENDING_EXECUTION:
                raise ExecutionConflictError("Only pending execution records can be cancelled.")
            now = self.clock()
            steps = tuple(
                replace(item, status=StepExecutionStatus.CANCELLED, completed_at=now)
                if item.status is StepExecutionStatus.PENDING
                else item
                for item in record.step_records
            )
            updated = replace(
                record, status=ExecutionStatus.CANCELLED, completed_at=now, step_records=steps
            )
            updated = self._with_event(
                updated, "execution_cancelled", "cancelled", "Pending execution cancelled."
            )
            self._records[execution_id] = updated
            return updated

    def _record(self, execution_id: str) -> AgentPlanExecutionRecord:
        try:
            return self._records[execution_id]
        except KeyError as error:
            raise ExecutionNotFoundError("Execution record not found.") from error

    @staticmethod
    def _step(
        record: AgentPlanExecutionRecord, step_index: int
    ) -> tuple[int, AgentPlanStepExecutionRecord]:
        for position, step in enumerate(record.step_records):
            if step.step_index == step_index:
                return position, step
        raise ExecutionNotFoundError("Execution step not found.")

    def _with_event(
        self,
        record: AgentPlanExecutionRecord,
        event_type: str,
        outcome: str,
        message: str,
        **fields: object,
    ) -> AgentPlanExecutionRecord:
        event = self._event(
            record.execution_id, record.review_id, event_type, outcome, message, **fields
        )
        return replace(record, audit_events=(*record.audit_events, event))

    def _event(
        self,
        execution_id: str | None,
        review_id: str,
        event_type: str,
        outcome: str,
        message: str,
        **fields: object,
    ) -> ExecutionAuditEvent:
        return ExecutionAuditEvent(
            event_id=f"audit_{secrets.token_urlsafe(12)}",
            event_type=event_type,
            timestamp=self.clock(),
            execution_id=execution_id,
            review_id=review_id,
            outcome=outcome,
            safe_message=message,
            step_index=fields.get("step_index")
            if isinstance(fields.get("step_index"), int)
            else None,
            tool_id=fields.get("tool_id") if isinstance(fields.get("tool_id"), str) else None,
            operation_id=fields.get("operation_id")
            if isinstance(fields.get("operation_id"), str)
            else None,
        )

    def _make_room(self) -> None:
        if len(self._records) < self.max_records:
            return
        terminal = sorted(
            (
                item
                for item in self._records.values()
                if item.status
                in {ExecutionStatus.COMPLETED, ExecutionStatus.FAILED, ExecutionStatus.CANCELLED}
            ),
            key=lambda item: (item.completed_at or item.created_at, item.execution_id),
        )
        for item in terminal:
            del self._records[item.execution_id]
            self._by_review.pop(item.review_id, None)
            if len(self._records) < self.max_records:
                return
        raise ExecutionCapacityError("Execution capacity is full of active records.")
