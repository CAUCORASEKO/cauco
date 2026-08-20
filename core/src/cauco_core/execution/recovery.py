from dataclasses import dataclass
from enum import StrEnum


class RecoveryDecision(StrEnum):
    RETRY = "retry"
    SKIP = "skip"
    REPLAN_REQUIRED = "replan_required"
    ABORT = "abort"


@dataclass(frozen=True, slots=True)
class RecoveryContext:
    tool_id: str
    operation_id: str
    error_code: str
    execution_performed: bool
    mutation_performed: bool
    attempt_count: int


class RecoveryPolicy:
    """Deterministic, fail-closed recovery policy for TaskRuntime v1."""

    max_retries = 1
    _retry_safe_operations = frozenset(
        {
            ("git", "status"),
            ("filesystem", "list_directory"),
            ("filesystem", "read_file"),
        }
    )
    _transient_errors = frozenset({"timeout", "temporarily_unavailable"})
    _replan_errors = frozenset(
        {
            "stale_state",
            "index_stale",
            "worktree_stale",
            "remote_state_stale",
        }
    )
    _never_retry_errors = frozenset(
        {
            "confirmation_failed",
            "confirmation_phrase_mismatch",
            "digest_mismatch",
            "forbidden",
            "integrity_failure",
            "snapshot_mismatch",
            "sensitive_path",
            "verification_failed",
        }
    )

    def evaluate(self, context: RecoveryContext) -> RecoveryDecision:
        # ExecutionPlan v1 has no immutable optional-step marker. SKIP therefore
        # remains a supported runtime decision but is never selected automatically.
        if context.mutation_performed:
            return RecoveryDecision.ABORT
        if context.error_code in self._replan_errors:
            return RecoveryDecision.REPLAN_REQUIRED
        if context.error_code in self._never_retry_errors:
            return RecoveryDecision.ABORT
        if (
            not context.mutation_performed
            and (context.tool_id, context.operation_id) in self._retry_safe_operations
            and context.error_code in self._transient_errors
            and context.attempt_count <= self.max_retries
        ):
            return RecoveryDecision.RETRY
        return RecoveryDecision.ABORT
