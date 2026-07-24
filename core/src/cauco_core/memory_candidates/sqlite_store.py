from __future__ import annotations

import json
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

from cauco_core.learning.models import LessonCategory
from cauco_core.memory_candidates.models import (
    MemoryCandidateDisposition,
    MemoryCandidateLesson,
    MemoryCandidateRecord,
    MemoryCandidateStatus,
    MemoryCandidateTarget,
)
from cauco_core.memory_candidates.store import MemoryCandidateStore
from cauco_core.persistence import SQLiteDatabase


class SQLiteMemoryCandidateStore(MemoryCandidateStore):
    def __init__(
        self,
        database: SQLiteDatabase,
        *,
        ttl: timedelta = timedelta(days=7),
        max_records: int = 500,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.database = database
        self.database.initialize()
        super().__init__(
            ttl=ttl,
            max_records=max_records,
            clock=clock,
        )
        self._restore()

    def create(self, **kwargs: Any) -> MemoryCandidateRecord:
        with self._lock:
            previous = dict(self._records)
            record = super().create(**kwargs)

            if record.candidate_id in previous and previous[record.candidate_id] == record:
                return record

            evicted_ids = set(previous) - set(self._records)

            try:
                with self.database.transaction() as connection:
                    for candidate_id in evicted_ids:
                        connection.execute(
                            """
                            DELETE FROM memory_candidates
                            WHERE candidate_id = ?
                            """,
                            (candidate_id,),
                        )

                    self._insert(connection, record)
            except Exception:
                self._records = previous
                raise

            return record

    def get(self, candidate_id: str) -> MemoryCandidateRecord:
        with self._lock:
            previous = dict(self._records)
            record = super().get(candidate_id)

            if previous.get(candidate_id) == record:
                return record

            try:
                self._persist_record(record)
            except Exception:
                self._records = previous
                raise

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
        with self._lock:
            previous = dict(self._records)
            records = super().list(
                experience_id=experience_id,
                review_id=review_id,
                status=status,
                target=target,
                limit=limit,
            )

            changed = tuple(
                record
                for candidate_id, record in self._records.items()
                if previous.get(candidate_id) != record
            )

            if not changed:
                return records

            try:
                with self.database.transaction() as connection:
                    for record in changed:
                        self._update(connection, record)
            except Exception:
                self._records = previous
                raise

            return records

    def approve(
        self,
        candidate_id: str,
        review_note: str | None = None,
    ) -> MemoryCandidateRecord:
        with self._lock:
            previous = dict(self._records)

            try:
                record = super().approve(
                    candidate_id,
                    review_note,
                )
                self._persist_record(record)
            except Exception:
                self._records = previous
                raise

            return record

    def reject(
        self,
        candidate_id: str,
        disposition: MemoryCandidateDisposition,
        review_note: str | None = None,
    ) -> MemoryCandidateRecord:
        with self._lock:
            previous = dict(self._records)

            try:
                record = super().reject(
                    candidate_id,
                    disposition,
                    review_note,
                )
                self._persist_record(record)
            except Exception:
                self._records = previous
                raise

            return record

    def _persist_record(
        self,
        record: MemoryCandidateRecord,
    ) -> None:
        with self.database.transaction() as connection:
            self._update(connection, record)

    @staticmethod
    def _insert(
        connection: Any,
        record: MemoryCandidateRecord,
    ) -> None:
        connection.execute(
            """
            INSERT INTO memory_candidates (
                candidate_id,
                experience_id,
                verification_id,
                execution_id,
                review_id,
                snapshot_digest,
                category,
                target,
                status,
                disposition,
                confidence,
                created_at,
                expires_at,
                reviewed_at,
                record_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            _database_values(record),
        )

    @staticmethod
    def _update(
        connection: Any,
        record: MemoryCandidateRecord,
    ) -> None:
        connection.execute(
            """
            UPDATE memory_candidates
            SET
                status = ?,
                disposition = ?,
                reviewed_at = ?,
                record_json = ?
            WHERE candidate_id = ?
            """,
            (
                record.status.value,
                (record.disposition.value if record.disposition is not None else None),
                _timestamp(record.reviewed_at),
                _record_json(record),
                record.candidate_id,
            ),
        )

    def _restore(self) -> None:
        with self._lock, self.database.connection() as connection:
            records = tuple(
                _record_from_json(str(row["record_json"]))
                for row in connection.execute(
                    """
                    SELECT record_json
                    FROM memory_candidates
                    ORDER BY created_at ASC, candidate_id ASC
                    """
                )
            )
            self._records = {record.candidate_id: record for record in records}


def _timestamp(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.astimezone(UTC).isoformat()


def _database_values(
    record: MemoryCandidateRecord,
) -> tuple[object, ...]:
    return (
        record.candidate_id,
        record.experience_id,
        record.verification_id,
        record.execution_id,
        record.review_id,
        record.snapshot_digest,
        record.lesson.category.value,
        record.target.value,
        record.status.value,
        (record.disposition.value if record.disposition is not None else None),
        record.lesson.confidence,
        _timestamp(record.created_at),
        _timestamp(record.expires_at),
        _timestamp(record.reviewed_at),
        _record_json(record),
    )


def _record_json(record: MemoryCandidateRecord) -> str:
    return json.dumps(
        {
            "candidate_id": record.candidate_id,
            "experience_id": record.experience_id,
            "verification_id": record.verification_id,
            "execution_id": record.execution_id,
            "review_id": record.review_id,
            "snapshot_digest": record.snapshot_digest,
            "lesson": {
                "category": record.lesson.category.value,
                "observation": record.lesson.observation,
                "lesson": record.lesson.lesson,
                "confidence": record.lesson.confidence,
                "tool_id": record.lesson.tool_id,
                "operation_id": record.lesson.operation_id,
                "step_index": record.lesson.step_index,
            },
            "target": record.target.value,
            "status": record.status.value,
            "disposition": (record.disposition.value if record.disposition is not None else None),
            "rationale": record.rationale,
            "created_at": _timestamp(record.created_at),
            "expires_at": _timestamp(record.expires_at),
            "reviewed_at": _timestamp(record.reviewed_at),
            "review_note": record.review_note,
            "method": record.method,
        },
        sort_keys=True,
        separators=(",", ":"),
    )


def _record_from_json(value: str) -> MemoryCandidateRecord:
    payload = json.loads(value)

    if not isinstance(payload, dict):
        raise ValueError("Stored memory candidate JSON must be an object.")

    lesson_payload = payload.get("lesson")
    if not isinstance(lesson_payload, dict):
        raise ValueError("Stored memory candidate lesson must be an object.")

    return MemoryCandidateRecord(
        candidate_id=str(payload["candidate_id"]),
        experience_id=str(payload["experience_id"]),
        verification_id=str(payload["verification_id"]),
        execution_id=str(payload["execution_id"]),
        review_id=str(payload["review_id"]),
        snapshot_digest=str(payload["snapshot_digest"]),
        lesson=MemoryCandidateLesson(
            category=LessonCategory(str(lesson_payload["category"])),
            observation=str(lesson_payload["observation"]),
            lesson=str(lesson_payload["lesson"]),
            confidence=float(lesson_payload["confidence"]),
            tool_id=(
                str(lesson_payload["tool_id"])
                if lesson_payload.get("tool_id") is not None
                else None
            ),
            operation_id=(
                str(lesson_payload["operation_id"])
                if lesson_payload.get("operation_id") is not None
                else None
            ),
            step_index=(
                int(lesson_payload["step_index"])
                if lesson_payload.get("step_index") is not None
                else None
            ),
        ),
        target=MemoryCandidateTarget(str(payload["target"])),
        status=MemoryCandidateStatus(str(payload["status"])),
        disposition=(
            MemoryCandidateDisposition(str(payload["disposition"]))
            if payload.get("disposition") is not None
            else None
        ),
        rationale=str(payload["rationale"]),
        created_at=datetime.fromisoformat(str(payload["created_at"])),
        expires_at=datetime.fromisoformat(str(payload["expires_at"])),
        reviewed_at=(
            datetime.fromisoformat(str(payload["reviewed_at"]))
            if payload.get("reviewed_at") is not None
            else None
        ),
        review_note=(
            str(payload["review_note"]) if payload.get("review_note") is not None else None
        ),
        method=str(payload["method"]),
    )
