# ruff: noqa: E501
from typing import ClassVar

import cauco_core.memory_candidates.models as models
from cauco_core.learning.models import LessonCategory
from cauco_core.learning.store import (
    ExperienceNotFoundError,
    ExperienceStore,
)
from cauco_core.memory_candidates.store import MemoryCandidateStore, deterministic_candidate_id


class MemoryCandidateService:
    METHOD = "deterministic_experience_memory_candidate_v1"
    RATIONALES: ClassVar = {
        LessonCategory.PLANNING: "This reusable lesson may improve the construction of future plans.",
        LessonCategory.EXECUTION: "This reusable lesson may improve how future approved operations are performed.",
        LessonCategory.VERIFICATION: "This reusable lesson may improve the definition and evaluation of future success criteria.",
        LessonCategory.TOOL_RELIABILITY: "This reusable lesson may improve future decisions involving this tool-operation pair.",
    }

    def __init__(
        self, *, experience_store: ExperienceStore, candidate_store: MemoryCandidateStore
    ) -> None:
        self.experience_store, self.candidate_store = experience_store, candidate_store

    def create_for_experience(
        self,
        experience_id: str,
    ) -> tuple[models.MemoryCandidateRecord, ...]:
        try:
            experience = self.experience_store.get(experience_id)
        except ExperienceNotFoundError as error:
            raise models.MemoryCandidateNotFoundError("Experience record not found.") from error
        lessons = []
        seen = set()
        for item in experience.lesson_candidates:
            if not item.reusable:
                continue
            key = (item.observation, item.lesson)
            if key in seen:
                continue
            seen.add(key)
            lesson = models.MemoryCandidateLesson(
                item.category,
                item.observation,
                item.lesson,
                item.confidence,
                item.tool_id,
                item.operation_id,
                item.step_index,
            )
            lessons.append(
                self.candidate_store.create(
                    candidate_id=deterministic_candidate_id(experience_id, lesson),
                    experience_id=experience.experience_id,
                    verification_id=experience.verification_id,
                    execution_id=experience.execution_id,
                    review_id=experience.review_id,
                    snapshot_digest=experience.snapshot_digest,
                    lesson=lesson,
                    rationale=self.RATIONALES[item.category],
                    method=self.METHOD,
                )
            )
        if not lessons:
            raise models.MemoryCandidateValidationError("Experience has no reusable lessons.")
        return tuple(
            sorted(
                lessons,
                key=lambda r: (
                    r.lesson.category,
                    r.lesson.step_index or 0,
                    r.lesson.tool_id or "",
                    r.lesson.operation_id or "",
                    r.candidate_id,
                ),
            )
        )
