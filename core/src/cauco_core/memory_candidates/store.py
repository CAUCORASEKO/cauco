import hashlib
import json
import secrets
from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from threading import RLock

from cauco_core.memory_candidates.models import (
    MemoryCandidateCapacityError,
    MemoryCandidateConflictError,
    MemoryCandidateDisposition,
    MemoryCandidateExpiredError,
    MemoryCandidateLesson,
    MemoryCandidateNotFoundError,
    MemoryCandidateRecord,
    MemoryCandidateStatus,
    MemoryCandidateTarget,
)


class MemoryCandidateStore:
    def __init__(
        self,
        *,
        ttl: timedelta = timedelta(days=7),
        max_records: int = 500,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        if ttl.total_seconds() <= 0:
            raise ValueError("Candidate TTL must be positive.")
        if not 1 <= max_records <= 10_000:
            raise ValueError("Candidate capacity must be between 1 and 10000.")
        self.ttl, self.max_records = ttl, max_records
        self.clock = clock or (lambda: datetime.now(tz=UTC))
        self._records: dict[str, MemoryCandidateRecord] = {}
        self._lock = RLock()

    def create(
        self,
        *,
        experience_id: str,
        verification_id: str,
        execution_id: str,
        review_id: str,
        snapshot_digest: str,
        lesson: MemoryCandidateLesson,
        rationale: str,
        method: str,
        candidate_id: str | None = None,
    ) -> MemoryCandidateRecord:
        with self._lock:
            if candidate_id and candidate_id in self._records:
                return self._records[candidate_id]
            self._make_room()
            created = self.clock()
            record = MemoryCandidateRecord(
                candidate_id=candidate_id or f"memory_candidate_{secrets.token_urlsafe(18)}",
                experience_id=experience_id,
                verification_id=verification_id,
                execution_id=execution_id,
                review_id=review_id,
                snapshot_digest=snapshot_digest,
                lesson=lesson,
                target=MemoryCandidateTarget.LEARNING,
                status=MemoryCandidateStatus.PENDING_REVIEW,
                disposition=None,
                rationale=rationale,
                created_at=created,
                expires_at=created + self.ttl,
                reviewed_at=None,
                review_note=None,
                method=method,
            )
            self._records[record.candidate_id] = record
            return record

    def get(self, candidate_id: str) -> MemoryCandidateRecord:
        with self._lock:
            record, _ = self._expire(self._record(candidate_id))
            return record

    def list(
        self,
        *,
        experience_id: str | None = None,
        review_id: str | None = None,
        status: MemoryCandidateStatus | None = None,
        target: MemoryCandidateTarget | None = None,
        limit: int = 20,
    ) -> tuple[MemoryCandidateRecord, ...]:
        if not 1 <= limit <= 100:
            raise ValueError("Candidate list limit must be between 1 and 100.")
        with self._lock:
            for record in tuple(self._records.values()):
                self._expire(record)
            return tuple(
                sorted(
                    (
                        r
                        for r in self._records.values()
                        if (experience_id is None or r.experience_id == experience_id)
                        and (review_id is None or r.review_id == review_id)
                        and (status is None or r.status is status)
                        and (target is None or r.target is target)
                    ),
                    key=lambda r: (r.created_at, r.candidate_id),
                    reverse=True,
                )[:limit]
            )

    def for_experience(self, experience_id: str) -> tuple[MemoryCandidateRecord, ...]:
        return self.list(experience_id=experience_id, limit=100)

    def approve(self, candidate_id: str, review_note: str | None = None) -> MemoryCandidateRecord:
        return self._review(
            candidate_id,
            MemoryCandidateStatus.APPROVED,
            MemoryCandidateDisposition.PROMOTE_TO_MEMORY,
            review_note,
        )

    def reject(
        self,
        candidate_id: str,
        disposition: MemoryCandidateDisposition,
        review_note: str | None = None,
    ) -> MemoryCandidateRecord:
        if disposition is MemoryCandidateDisposition.PROMOTE_TO_MEMORY:
            raise ValueError("Rejected candidates cannot promote to memory.")
        return self._review(candidate_id, MemoryCandidateStatus.REJECTED, disposition, review_note)

    def _review(
        self,
        candidate_id: str,
        status: MemoryCandidateStatus,
        disposition: MemoryCandidateDisposition,
        note: str | None,
    ) -> MemoryCandidateRecord:
        with self._lock:
            record, _ = self._expire(self._record(candidate_id))
            if record.status is MemoryCandidateStatus.EXPIRED:
                raise MemoryCandidateExpiredError("The memory candidate has expired.")
            if record.status is not MemoryCandidateStatus.PENDING_REVIEW:
                raise MemoryCandidateConflictError("The memory candidate was already reviewed.")
            note = note.strip() if note else None
            if note == "":
                note = None
            if note and len(note) > 2000:
                raise ValueError("Review note must not exceed 2000 characters.")
            updated = replace(
                record,
                status=status,
                disposition=disposition,
                reviewed_at=self.clock(),
                review_note=note,
            )
            self._records[candidate_id] = updated
            return updated

    def _record(self, candidate_id: str) -> MemoryCandidateRecord:
        if candidate_id not in self._records:
            raise MemoryCandidateNotFoundError("Memory candidate not found.")
        return self._records[candidate_id]

    def _expire(
        self,
        record: MemoryCandidateRecord,
    ) -> tuple[MemoryCandidateRecord, bool]:
        if (
            record.status is MemoryCandidateStatus.PENDING_REVIEW
            and self.clock() >= record.expires_at
        ):
            expired = replace(
                record,
                status=MemoryCandidateStatus.EXPIRED,
                disposition=None,
                reviewed_at=None,
                review_note=None,
            )
            self._records[record.candidate_id] = expired
            return expired, True
        return record, False

    def _make_room(self) -> None:
        if len(self._records) < self.max_records:
            return

        for record in tuple(self._records.values()):
            self._expire(record)

        terminal = [
            record
            for record in self._records.values()
            if record.status is not MemoryCandidateStatus.PENDING_REVIEW
        ]
        if not terminal:
            raise MemoryCandidateCapacityError("Only active pending candidates remain.")
        oldest = min(terminal, key=lambda r: (r.created_at, r.candidate_id))
        del self._records[oldest.candidate_id]


def deterministic_candidate_id(experience_id: str, lesson: MemoryCandidateLesson) -> str:
    payload = {
        "experience_id": experience_id,
        "category": lesson.category.value,
        "observation": lesson.observation,
        "lesson": lesson.lesson,
        "tool_id": lesson.tool_id,
        "operation_id": lesson.operation_id,
        "step_index": lesson.step_index,
        "target": MemoryCandidateTarget.LEARNING.value,
    }
    digest = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return f"memory_candidate_{digest}"
