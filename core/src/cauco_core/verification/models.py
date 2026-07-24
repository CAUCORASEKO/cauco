import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from types import MappingProxyType


class VerificationOutcome(StrEnum):
    SUCCEEDED = "succeeded"
    PARTIAL_SUCCESS = "partial_success"
    FAILED = "failed"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"


class VerificationRecommendation(StrEnum):
    COMPLETE = "complete"
    STOP = "stop"
    REQUEST_REVIEW = "request_review"


@dataclass(frozen=True, slots=True)
class StepVerificationResult:
    step_index: int
    tool_id: str
    operation_id: str
    outcome: VerificationOutcome
    method: str
    expected_conditions: tuple[str, ...] = ()
    observed_conditions: tuple[str, ...] = ()
    evidence_references: tuple[str, ...] = ()
    deviations: tuple[str, ...] = ()
    unresolved_conditions: tuple[str, ...] = ()
    rollback_available: bool | None = None

    def __post_init__(self) -> None:
        if self.step_index < 1:
            raise ValueError("Verification step index must be positive.")
        if not self.tool_id or not self.operation_id:
            raise ValueError("Verification step tool identity is required.")


@dataclass(frozen=True, slots=True)
class VerificationRecord:
    verification_id: str
    execution_id: str
    review_id: str
    snapshot_digest: str
    created_at: datetime
    outcome: VerificationOutcome
    recommendation: VerificationRecommendation
    method: str
    step_results: tuple[StepVerificationResult, ...]
    evidence_references: tuple[str, ...] = ()
    deviations: tuple[str, ...] = ()
    unresolved_conditions: tuple[str, ...] = ()
    rollback_available: bool | None = None
    metadata: Mapping[str, str | int | float | bool | None] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not re.fullmatch(
            r"verify_[A-Za-z0-9_-]{20,}",
            self.verification_id,
        ):
            raise ValueError("Verification ID must be opaque and URL-safe.")
        if not re.fullmatch(
            r"exec_[A-Za-z0-9_-]{20,}",
            self.execution_id,
        ):
            raise ValueError("Execution ID must be opaque and URL-safe.")
        if not re.fullmatch(r"[0-9a-f]{64}", self.snapshot_digest):
            raise ValueError("Verification snapshot digest must be a SHA-256 digest.")
        if not self.step_results:
            raise ValueError("Verification requires at least one step result.")
        object.__setattr__(
            self,
            "metadata",
            MappingProxyType(dict(self.metadata)),
        )


class VerificationError(RuntimeError):
    pass


class VerificationNotFoundError(VerificationError):
    pass


class VerificationConflictError(VerificationError):
    pass


class VerificationValidationError(VerificationError):
    pass


class VerificationCapacityError(VerificationError):
    pass
