import re
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from cauco_core.learning.models import LessonCategory


class MemoryCandidateStatus(StrEnum):
    PENDING_REVIEW = "pending_review"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"


class MemoryCandidateDisposition(StrEnum):
    PROMOTE_TO_MEMORY = "promote_to_memory"
    RETAIN_AS_EXPERIENCE_ONLY = "retain_as_experience_only"
    DISCARD = "discard"


class MemoryCandidateTarget(StrEnum):
    LEARNING = "learning"
    PROJECT_NOTE = "project_note"
    DECISION = "decision"


@dataclass(frozen=True, slots=True)
class MemoryCandidateLesson:
    category: LessonCategory
    observation: str
    lesson: str
    confidence: float
    tool_id: str | None = None
    operation_id: str | None = None
    step_index: int | None = None

    def __post_init__(self) -> None:
        if not self.observation.strip() or not self.lesson.strip():
            raise ValueError("Candidate lesson text is required.")
        if not 0 <= self.confidence <= 1:
            raise ValueError("Candidate confidence must be between 0 and 1.")
        if self.step_index is not None and self.step_index < 1:
            raise ValueError("Candidate step index must be positive.")


@dataclass(frozen=True, slots=True)
class MemoryCandidateRecord:
    candidate_id: str
    experience_id: str
    verification_id: str
    execution_id: str
    review_id: str
    snapshot_digest: str
    lesson: MemoryCandidateLesson
    target: MemoryCandidateTarget
    status: MemoryCandidateStatus
    disposition: MemoryCandidateDisposition | None
    rationale: str
    created_at: datetime
    expires_at: datetime
    reviewed_at: datetime | None
    review_note: str | None
    method: str

    def __post_init__(self) -> None:
        patterns = {
            "candidate_id": (r"memory_candidate_[A-Za-z0-9_-]{20,}", self.candidate_id),
            "experience_id": (r"experience_[A-Za-z0-9_-]{20,}", self.experience_id),
            "verification_id": (r"verify_[A-Za-z0-9_-]{20,}", self.verification_id),
            "execution_id": (r"exec_[A-Za-z0-9_-]{20,}", self.execution_id),
        }
        if any(not re.fullmatch(pattern, value) for pattern, value in patterns.values()):
            raise ValueError("Memory candidate IDs must be opaque and URL-safe.")
        if not re.fullmatch(r"[0-9a-f]{64}", self.snapshot_digest):
            raise ValueError("Candidate snapshot digest must be a SHA-256 digest.")
        if not self.rationale.strip() or not self.method.strip():
            raise ValueError("Candidate rationale and method are required.")
        for value in (self.created_at, self.expires_at, self.reviewed_at):
            if value is not None and value.tzinfo is None:
                raise ValueError("Candidate timestamps must include a timezone.")
        if self.expires_at <= self.created_at:
            raise ValueError("Candidate expiration must be after creation.")
        if self.status is MemoryCandidateStatus.PENDING_REVIEW and (
            self.disposition or self.reviewed_at
        ):
            raise ValueError("Pending candidates cannot be reviewed.")
        if (
            self.status is MemoryCandidateStatus.APPROVED
            and self.disposition is not MemoryCandidateDisposition.PROMOTE_TO_MEMORY
        ):
            raise ValueError("Approved candidates must promote to memory.")
        if self.status is MemoryCandidateStatus.REJECTED and self.disposition not in {
            MemoryCandidateDisposition.RETAIN_AS_EXPERIENCE_ONLY,
            MemoryCandidateDisposition.DISCARD,
        }:
            raise ValueError("Rejected candidates require a rejection disposition.")
        if (
            self.status
            in {
                MemoryCandidateStatus.APPROVED,
                MemoryCandidateStatus.REJECTED,
            }
            and self.reviewed_at is None
        ):
            raise ValueError("Reviewed candidates require reviewed_at.")
        if self.status is MemoryCandidateStatus.EXPIRED and (
            self.disposition is not None
            or self.reviewed_at is not None
            or self.review_note is not None
        ):
            raise ValueError("Expired candidates cannot contain review state.")


class MemoryCandidateError(RuntimeError):
    pass


class MemoryCandidateNotFoundError(MemoryCandidateError):
    pass


class MemoryCandidateConflictError(MemoryCandidateError):
    pass


class MemoryCandidateValidationError(MemoryCandidateError):
    pass


class MemoryCandidateCapacityError(MemoryCandidateError):
    pass


class MemoryCandidateExpiredError(MemoryCandidateError):
    pass
