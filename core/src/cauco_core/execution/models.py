import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from types import MappingProxyType

from cauco_tools import ToolExecutionResult


class ExecutionStatus(StrEnum):
    PENDING_EXECUTION = "pending_execution"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class StepExecutionStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"
    CANCELLED = "cancelled"


@dataclass(frozen=True, slots=True)
class ExecutionAuditEvent:
    event_id: str
    event_type: str
    timestamp: datetime
    execution_id: str | None
    review_id: str
    outcome: str
    safe_message: str
    step_index: int | None = None
    tool_id: str | None = None
    operation_id: str | None = None
    metadata: Mapping[str, str | int | float | bool | None] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "metadata", MappingProxyType(dict(self.metadata)))


@dataclass(frozen=True, slots=True)
class AgentPlanStepExecutionRecord:
    step_index: int
    tool_id: str
    operation_id: str
    target: str | None
    status: StepExecutionStatus
    started_at: datetime | None = None
    completed_at: datetime | None = None
    result: ToolExecutionResult | None = None
    error: str | None = None
    execution_performed: bool = False


@dataclass(frozen=True, slots=True)
class AgentPlanExecutionRecord:
    execution_id: str
    review_id: str
    snapshot_digest: str
    status: ExecutionStatus
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
    current_step_index: int | None
    total_steps: int
    step_records: tuple[AgentPlanStepExecutionRecord, ...]
    execution_performed: bool
    failure_reason: str | None
    audit_events: tuple[ExecutionAuditEvent, ...]
    warning: str = "Execution is limited to explicitly requested allowlisted read-only steps."

    def __post_init__(self) -> None:
        if not re.fullmatch(r"exec_[A-Za-z0-9_-]{20,}", self.execution_id):
            raise ValueError("Execution ID must be opaque and URL-safe.")
        if not re.fullmatch(r"[0-9a-f]{64}", self.snapshot_digest):
            raise ValueError("Execution snapshot digest must be a SHA-256 digest.")
        if self.total_steps != len(self.step_records):
            raise ValueError("Execution step count is inconsistent.")


class ExecutionError(RuntimeError):
    pass


class ExecutionNotFoundError(ExecutionError):
    pass


class ExecutionConflictError(ExecutionError):
    pass


class ExecutionValidationError(ExecutionError):
    pass


class ExecutionForbiddenError(ExecutionError):
    pass


class ExecutionCapacityError(ExecutionError):
    pass
