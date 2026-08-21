from collections.abc import Callable
from dataclasses import asdict
from datetime import UTC, datetime

from cauco_agents import (
    AgentPlanReviewRecord,
    AgentPlanReviewStatus,
    CalendarListEventsInput,
    EmailListMessagesInput,
)
from cauco_tools import (
    ToolAdapterRegistry,
    ToolExecutionError,
    ToolExecutionRequest,
    ToolExecutionResult,
    ToolExecutionTimeoutError,
    ToolRegistry,
)

from cauco_core.agents.review_store import (
    AgentPlanReviewStore,
    PlanReviewIntegrityError,
    PlanReviewNotFoundError,
)
from cauco_core.execution.models import (
    AgentPlanExecutionRecord,
    AgentPlanStepExecutionRecord,
    ExecutionConflictError,
    ExecutionForbiddenError,
    ExecutionNotFoundError,
    ExecutionValidationError,
    StepExecutionStatus,
)
from cauco_core.execution.policy import WorkspacePolicy
from cauco_core.execution.store import ExecutionStore


class ExecutionService:
    def __init__(
        self,
        review_store: AgentPlanReviewStore,
        tool_registry: ToolRegistry,
        adapter_registry: ToolAdapterRegistry,
        execution_store: ExecutionStore,
        workspace_policy: WorkspacePolicy | None,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.review_store = review_store
        self.tool_registry = tool_registry
        self.adapter_registry = adapter_registry
        self.execution_store = execution_store
        self.workspace_policy = workspace_policy
        self.clock = clock or (lambda: datetime.now(tz=UTC))

    def create(self, review_id: str) -> AgentPlanExecutionRecord:
        try:
            review = self.review_store.get(review_id)
            self._validate_review(review)
        except (
            PlanReviewNotFoundError,
            PlanReviewIntegrityError,
            ExecutionConflictError,
        ):
            self.execution_store.record_rejected_attempt(
                review_id, "Execution creation was rejected."
            )
            raise
        steps: list[AgentPlanStepExecutionRecord] = []
        executable_count = 0
        for plan_step in review.plan.steps:
            reference = plan_step.tool_reference
            if reference is None:
                continue
            validation = self.tool_registry.validate(reference.tool_id, reference.operation_id)
            executable = (
                validation.valid
                and validation.runtime_execution_allowed
                and self.adapter_registry.exists(reference.tool_id, reference.operation_id)
            )
            if executable:
                executable_count += 1
            steps.append(
                AgentPlanStepExecutionRecord(
                    step_index=plan_step.order,
                    tool_id=reference.tool_id,
                    operation_id=reference.operation_id,
                    target=reference.target,
                    status=(
                        StepExecutionStatus.PENDING if executable else StepExecutionStatus.SKIPPED
                    ),
                    error=None if executable else "Operation is not runtime-enabled.",
                )
            )
        record = self.execution_store.create(review.review_id, review.snapshot_digest, tuple(steps))
        record = self.execution_store.append_event(
            record.execution_id,
            "integrity_verified",
            "success",
            "Approved snapshot integrity verified.",
        )
        if executable_count == 0:
            self.execution_store.fail_before_start(
                record.execution_id, "The approved plan contains no runtime-enabled steps."
            )
            raise ExecutionConflictError("The approved plan contains no runtime-enabled steps.")
        return record

    def execute_step(
        self,
        execution_id: str,
        step_index: int,
        *,
        timeout_seconds: float = 5.0,
        max_output_chars: int = 20_000,
        max_chars: int | None = None,
        max_entries: int | None = None,
    ) -> AgentPlanExecutionRecord:
        record = self.execution_store.get(execution_id)
        review = self.review_store.get(record.review_id)
        self._validate_review(review)
        if review.snapshot_digest != record.snapshot_digest:
            self._deny(record, step_index, "Snapshot digest does not match the execution record.")
            raise ExecutionConflictError("Snapshot digest verification failed.")
        plan_step = next((item for item in review.plan.steps if item.order == step_index), None)
        if plan_step is None or plan_step.tool_reference is None:
            self._deny(record, step_index, "Requested plan step does not exist.")
            raise ExecutionNotFoundError("Requested plan step does not exist.")
        reference = plan_step.tool_reference
        validation = self.tool_registry.validate(reference.tool_id, reference.operation_id)
        if not validation.valid or not validation.runtime_execution_allowed:
            self._deny(record, step_index, "Operation is not allowed for runtime execution.")
            raise ExecutionConflictError("Operation is not allowed for runtime execution.")
        if validation.preview_required:
            self._deny(record, step_index, "Mutation requires preview and separate confirmation.")
            raise ExecutionConflictError(
                "Mutations cannot run through the read-only execution endpoint."
            )
        if not self.adapter_registry.exists(reference.tool_id, reference.operation_id):
            self._deny(record, step_index, "No runtime adapter is available.")
            raise ExecutionConflictError("No runtime adapter is available.")
        try:
            arguments = self._arguments(
                reference.tool_id,
                reference.operation_id,
                reference.target,
                plan_step.operation_input,
                max_chars=max_chars,
                max_entries=max_entries,
            )
        except (ExecutionForbiddenError, ExecutionValidationError, ExecutionConflictError):
            self._deny(record, step_index, "Operation arguments were denied by workspace policy.")
            raise
        request = ToolExecutionRequest(
            tool_id=reference.tool_id,
            operation_id=reference.operation_id,
            arguments=arguments,
            timeout_seconds=timeout_seconds,
            max_output_chars=max_output_chars,
        )
        self.execution_store.append_event(
            execution_id,
            "tool_validated",
            "success",
            "Registered runtime operation validated.",
            step_index=step_index,
            tool_id=reference.tool_id,
            operation_id=reference.operation_id,
        )
        self.execution_store.start_step(execution_id, step_index)
        adapter = self.adapter_registry.get(reference.tool_id, reference.operation_id)
        try:
            result = adapter.execute(request)
        except ToolExecutionTimeoutError as error:
            failed_result = self._failed_result(
                execution_id, step_index, reference.tool_id, reference.operation_id, error
            )
            failed = self.execution_store.finish_step(
                execution_id,
                step_index,
                result=failed_result,
                error=error.safe_message,
                performed=True,
            )
            return self.execution_store.append_event(
                failed.execution_id,
                "timeout",
                "failed",
                "Tool operation timed out.",
                step_index=step_index,
                tool_id=reference.tool_id,
                operation_id=reference.operation_id,
            )
        except ToolExecutionError as error:
            failed_result = self._failed_result(
                execution_id, step_index, reference.tool_id, reference.operation_id, error
            )
            return self.execution_store.finish_step(
                execution_id,
                step_index,
                result=failed_result,
                error=error.safe_message,
                performed=True,
            )
        return self.execution_store.finish_step(
            execution_id,
            step_index,
            result=result,
            error=result.error_message,
            performed=True,
        )

    def cancel(self, execution_id: str) -> AgentPlanExecutionRecord:
        return self.execution_store.cancel(execution_id)

    def _validate_review(self, review: AgentPlanReviewRecord) -> None:
        if review.status is not AgentPlanReviewStatus.APPROVED:
            raise ExecutionConflictError("Plan review is not approved.")
        if self.clock() >= review.expires_at:
            raise ExecutionConflictError("Plan review approval has expired.")
        if not review.execution_authorized or review.execution_performed:
            raise ExecutionConflictError("Plan review is not eligible for execution.")
        self.review_store.verify_integrity(review)

    def _arguments(
        self,
        tool_id: str,
        operation_id: str,
        target: str | None,
        operation_input: object | None,
        *,
        max_chars: int | None,
        max_entries: int | None,
    ) -> dict[str, object]:
        if tool_id == "git" and operation_id == "status":
            return {}
        if tool_id == "calendar" and operation_id == "list_events":
            if not isinstance(operation_input, CalendarListEventsInput):
                raise ExecutionValidationError(
                    "Approved calendar list step has invalid typed input."
                )
            return asdict(operation_input)
        if tool_id == "email" and operation_id == "list_messages":
            if not isinstance(operation_input, EmailListMessagesInput):
                raise ExecutionValidationError(
                    "Approved email message list step has invalid typed input."
                )
            return asdict(operation_input)
        if self.workspace_policy is None:
            raise ExecutionConflictError("No execution workspace is configured.")
        if tool_id == "filesystem" and operation_id == "list_directory":
            relative = self.workspace_policy.validate_relative(
                target or ".", expect="directory", allow_root=True
            )
            return {
                "relative_path": relative,
                **({"max_entries": max_entries} if max_entries is not None else {}),
            }
        if tool_id == "filesystem" and operation_id == "read_file":
            if target is None:
                raise ExecutionValidationError("Approved filesystem read step has no target.")
            relative = self.workspace_policy.validate_relative(target, expect="file")
            return {
                "relative_path": relative,
                **({"max_chars": max_chars} if max_chars is not None else {}),
            }
        raise ExecutionConflictError("Operation is not supported by the execution service.")

    def _deny(self, record: AgentPlanExecutionRecord, step_index: int, message: str) -> None:
        self.execution_store.append_event(
            record.execution_id,
            "operation_denied",
            "rejected",
            message,
            step_index=step_index,
        )

    def _failed_result(
        self,
        execution_id: str,
        step_index: int,
        tool_id: str,
        operation_id: str,
        error: ToolExecutionError,
    ) -> ToolExecutionResult:
        record = self.execution_store.get(execution_id)
        step = next(item for item in record.step_records if item.step_index == step_index)
        completed = self.clock()
        started = step.started_at or completed
        return ToolExecutionResult(
            tool_id=tool_id,
            operation_id=operation_id,
            success=False,
            started_at=started,
            completed_at=completed,
            duration_ms=max(0, round((completed - started).total_seconds() * 1000)),
            output="",
            error_code=error.code,
            error_message=error.safe_message,
            execution_performed=True,
        )
