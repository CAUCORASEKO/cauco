import secrets
from collections.abc import Callable
from datetime import UTC, datetime
from threading import RLock

from cauco_core.verification.models import (
    StepVerificationResult,
    VerificationCapacityError,
    VerificationConflictError,
    VerificationNotFoundError,
    VerificationOutcome,
    VerificationRecommendation,
    VerificationRecord,
)


class VerificationStore:
    def __init__(
        self,
        *,
        max_records: int = 100,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        if not 1 <= max_records <= 10_000:
            raise ValueError("Verification capacity must be between 1 and 10000.")
        self.max_records = max_records
        self.clock = clock or (lambda: datetime.now(tz=UTC))
        self._records: dict[str, VerificationRecord] = {}
        self._by_execution: dict[str, str] = {}
        self._lock = RLock()

    def create(
        self,
        *,
        execution_id: str,
        review_id: str,
        snapshot_digest: str,
        outcome: VerificationOutcome,
        recommendation: VerificationRecommendation,
        method: str,
        step_results: tuple[StepVerificationResult, ...],
        evidence_references: tuple[str, ...] = (),
        deviations: tuple[str, ...] = (),
        unresolved_conditions: tuple[str, ...] = (),
        rollback_available: bool | None = None,
    ) -> VerificationRecord:
        with self._lock:
            if execution_id in self._by_execution:
                raise VerificationConflictError(
                    "A verification record already exists for this execution."
                )

            self._make_room()

            record = VerificationRecord(
                verification_id=f"verify_{secrets.token_urlsafe(18)}",
                execution_id=execution_id,
                review_id=review_id,
                snapshot_digest=snapshot_digest,
                created_at=self.clock(),
                outcome=outcome,
                recommendation=recommendation,
                method=method,
                step_results=step_results,
                evidence_references=evidence_references,
                deviations=deviations,
                unresolved_conditions=unresolved_conditions,
                rollback_available=rollback_available,
            )
            self._records[record.verification_id] = record
            self._by_execution[execution_id] = record.verification_id
            return record

    def get(self, verification_id: str) -> VerificationRecord:
        with self._lock:
            try:
                return self._records[verification_id]
            except KeyError as error:
                raise VerificationNotFoundError("Verification record not found.") from error

    def for_execution(self, execution_id: str) -> VerificationRecord:
        with self._lock:
            verification_id = self._by_execution.get(execution_id)
            if verification_id is None:
                raise VerificationNotFoundError("Verification record not found.")
            return self._records[verification_id]

    def list(
        self,
        *,
        review_id: str | None = None,
        outcome: VerificationOutcome | None = None,
        limit: int = 20,
    ) -> tuple[VerificationRecord, ...]:
        if not 1 <= limit <= 100:
            raise ValueError("Verification list limit must be between 1 and 100.")

        with self._lock:
            records = (
                record
                for record in self._records.values()
                if (review_id is None or record.review_id == review_id)
                and (outcome is None or record.outcome is outcome)
            )
            return tuple(
                sorted(
                    records,
                    key=lambda item: (
                        item.created_at,
                        item.verification_id,
                    ),
                    reverse=True,
                )[:limit]
            )

    def _make_room(self) -> None:
        if len(self._records) < self.max_records:
            return

        oldest = min(
            self._records.values(),
            key=lambda item: (
                item.created_at,
                item.verification_id,
            ),
            default=None,
        )
        if oldest is None:
            raise VerificationCapacityError("Verification capacity is full.")

        del self._records[oldest.verification_id]
        self._by_execution.pop(oldest.execution_id, None)
