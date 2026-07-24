import re
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


class ExperienceOutcome(StrEnum):
    SUCCESS = "success"
    PARTIAL = "partial"
    FAILURE = "failure"
    INCONCLUSIVE = "inconclusive"


class LessonCategory(StrEnum):
    PLANNING = "planning"
    EXECUTION = "execution"
    VERIFICATION = "verification"
    TOOL_RELIABILITY = "tool_reliability"


@dataclass(frozen=True, slots=True)
class LessonCandidate:
    category: LessonCategory
    observation: str
    lesson: str
    confidence: float
    reusable: bool
    tool_id: str | None = None
    operation_id: str | None = None
    step_index: int | None = None

    def __post_init__(self) -> None:
        if not self.observation.strip() or not self.lesson.strip():
            raise ValueError("Lesson observation and lesson must not be empty.")
        if not 0 <= self.confidence <= 1:
            raise ValueError("Lesson confidence must be between 0 and 1.")
        if self.step_index is not None and self.step_index < 1:
            raise ValueError("Lesson step index must be positive.")


@dataclass(frozen=True, slots=True)
class ExperienceRecord:
    experience_id: str
    verification_id: str
    execution_id: str
    review_id: str
    snapshot_digest: str
    created_at: datetime
    outcome: ExperienceOutcome
    summary: str
    lesson_candidates: tuple[LessonCandidate, ...]
    memory_candidate: bool
    recommendation: str
    method: str

    def __post_init__(self) -> None:
        for prefix, value in (
            ("experience_", self.experience_id),
            ("verify_", self.verification_id),
            ("exec_", self.execution_id),
        ):
            if not re.fullmatch(prefix + r"[A-Za-z0-9_-]{20,}", value):
                raise ValueError("Experience IDs must be opaque and URL-safe.")
        if not re.fullmatch(r"[0-9a-f]{64}", self.snapshot_digest):
            raise ValueError("Experience snapshot digest must be a SHA-256 digest.")
        if not self.summary.strip() or not self.recommendation.strip() or not self.method.strip():
            raise ValueError("Experience summary, recommendation, and method are required.")
        if self.memory_candidate != any(lesson.reusable for lesson in self.lesson_candidates):
            raise ValueError("Experience memory candidate must reflect reusable lessons.")


class ExperienceError(RuntimeError):
    pass


class ExperienceNotFoundError(ExperienceError):
    pass


class ExperienceConflictError(ExperienceError):
    pass


class ExperienceCapacityError(ExperienceError):
    pass
