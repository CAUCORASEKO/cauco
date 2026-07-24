import secrets
from collections.abc import Callable
from datetime import UTC, datetime
from threading import RLock

from cauco_core.learning.models import (
    ExperienceCapacityError,
    ExperienceConflictError,
    ExperienceNotFoundError,
    ExperienceOutcome,
    ExperienceRecord,
    LessonCandidate,
)


class ExperienceStore:
    def __init__(
        self, *, max_records: int = 100, clock: Callable[[], datetime] | None = None
    ) -> None:
        if not 1 <= max_records <= 10_000:
            raise ValueError("Experience capacity must be between 1 and 10000.")
        self.max_records = max_records
        self.clock = clock or (lambda: datetime.now(tz=UTC))
        self._records: dict[str, ExperienceRecord] = {}
        self._by_verification: dict[str, str] = {}
        self._lock = RLock()

    def create(
        self,
        *,
        verification_id: str,
        execution_id: str,
        review_id: str,
        snapshot_digest: str,
        outcome: ExperienceOutcome,
        summary: str,
        lesson_candidates: tuple[LessonCandidate, ...],
        recommendation: str,
        method: str,
    ) -> ExperienceRecord:
        with self._lock:
            if verification_id in self._by_verification:
                raise ExperienceConflictError(
                    "An experience record already exists for this verification."
                )
            self._make_room()
            record = ExperienceRecord(
                experience_id=f"experience_{secrets.token_urlsafe(18)}",
                verification_id=verification_id,
                execution_id=execution_id,
                review_id=review_id,
                snapshot_digest=snapshot_digest,
                created_at=self.clock(),
                outcome=outcome,
                summary=summary,
                lesson_candidates=lesson_candidates,
                memory_candidate=any(item.reusable for item in lesson_candidates),
                recommendation=recommendation,
                method=method,
            )
            self._records[record.experience_id] = record
            self._by_verification[verification_id] = record.experience_id
            return record

    def get(self, experience_id: str) -> ExperienceRecord:
        with self._lock:
            try:
                return self._records[experience_id]
            except KeyError as error:
                raise ExperienceNotFoundError("Experience record not found.") from error

    def for_verification(self, verification_id: str) -> ExperienceRecord:
        with self._lock:
            experience_id = self._by_verification.get(verification_id)
            if experience_id is None:
                raise ExperienceNotFoundError("Experience record not found.")
            return self._records[experience_id]

    def list(
        self,
        *,
        review_id: str | None = None,
        outcome: ExperienceOutcome | None = None,
        memory_candidate: bool | None = None,
        limit: int = 20,
    ) -> tuple[ExperienceRecord, ...]:
        if not 1 <= limit <= 100:
            raise ValueError("Experience list limit must be between 1 and 100.")
        with self._lock:
            records = (
                item
                for item in self._records.values()
                if (review_id is None or item.review_id == review_id)
                and (outcome is None or item.outcome is outcome)
                and (memory_candidate is None or item.memory_candidate == memory_candidate)
            )
            return tuple(
                sorted(
                    records, key=lambda item: (item.created_at, item.experience_id), reverse=True
                )[:limit]
            )

    def _make_room(self) -> None:
        if len(self._records) < self.max_records:
            return
        oldest = min(
            self._records.values(),
            key=lambda item: (item.created_at, item.experience_id),
            default=None,
        )
        if oldest is None:
            raise ExperienceCapacityError("Experience capacity is full.")
        del self._records[oldest.experience_id]
        self._by_verification.pop(oldest.verification_id, None)
