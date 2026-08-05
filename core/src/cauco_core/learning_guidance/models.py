from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class LearningGuidance:
    candidate_id: str
    experience_id: str
    proposal_id: str
    category: str
    lesson: str
    confidence: float
    tool_id: str | None
    operation_id: str | None
    step_index: int | None
    reason_selected: str
    source_reference: str
    applied_at: datetime

    def __post_init__(self) -> None:
        for value in (
            self.candidate_id,
            self.experience_id,
            self.proposal_id,
            self.category,
            self.lesson,
            self.reason_selected,
            self.source_reference,
        ):
            if not isinstance(value, str) or not value.strip():
                raise ValueError("Learning guidance text and IDs are required.")
        if not 0 <= self.confidence <= 1:
            raise ValueError("Learning guidance confidence must be between 0 and 1.")
        if self.step_index is not None and self.step_index < 1:
            raise ValueError("Learning guidance step index must be positive.")
        if self.applied_at.tzinfo is None or self.applied_at.utcoffset() is None:
            raise ValueError("Learning guidance applied_at must include a timezone.")
