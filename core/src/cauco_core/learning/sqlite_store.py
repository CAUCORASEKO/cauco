from __future__ import annotations

import json
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from cauco_core.learning.models import (
    ExperienceOutcome,
    ExperienceRecord,
    LessonCandidate,
    LessonCategory,
)
from cauco_core.learning.store import ExperienceStore
from cauco_core.persistence import SQLiteDatabase


class SQLiteExperienceStore(ExperienceStore):
    def __init__(
        self,
        database: SQLiteDatabase,
        *,
        max_records: int = 100,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.database = database
        self.database.initialize()
        super().__init__(max_records=max_records, clock=clock)
        self._restore()

    def create(self, **kwargs: Any) -> ExperienceRecord:
        with self._lock:
            previous = dict(self._records)
            previous_index = dict(self._by_verification)
            record = super().create(**kwargs)
            evicted = set(previous) - set(self._records)
            try:
                with self.database.transaction() as connection:
                    for experience_id in evicted:
                        connection.execute(
                            "DELETE FROM experience_records WHERE experience_id = ?",
                            (experience_id,),
                        )
                    connection.execute(
                        """INSERT INTO experience_records
                        (experience_id, verification_id, execution_id, review_id, snapshot_digest,
                         outcome, memory_candidate, method, created_at, record_json)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                        (
                            record.experience_id,
                            record.verification_id,
                            record.execution_id,
                            record.review_id,
                            record.snapshot_digest,
                            record.outcome.value,
                            int(record.memory_candidate),
                            record.method,
                            _timestamp(record.created_at),
                            _record_json(record),
                        ),
                    )
            except Exception:
                self._records = previous
                self._by_verification = previous_index
                raise
            return record

    def _restore(self) -> None:
        with self._lock, self.database.connection() as connection:
            rows = connection.execute(
                "SELECT record_json FROM experience_records "
                "ORDER BY created_at ASC, experience_id ASC"
            ).fetchall()
            records = [_record_from_json(str(row["record_json"])) for row in rows]
            self._records = {record.experience_id: record for record in records}
            self._by_verification = {
                record.verification_id: record.experience_id for record in records
            }


def _record_json(record: ExperienceRecord) -> str:
    return json.dumps(
        {
            "experience_id": record.experience_id,
            "verification_id": record.verification_id,
            "execution_id": record.execution_id,
            "review_id": record.review_id,
            "snapshot_digest": record.snapshot_digest,
            "created_at": _timestamp(record.created_at),
            "outcome": record.outcome.value,
            "summary": record.summary,
            "lesson_candidates": [
                {
                    "category": item.category.value,
                    "observation": item.observation,
                    "lesson": item.lesson,
                    "confidence": item.confidence,
                    "reusable": item.reusable,
                    "tool_id": item.tool_id,
                    "operation_id": item.operation_id,
                    "step_index": item.step_index,
                }
                for item in record.lesson_candidates
            ],
            "memory_candidate": record.memory_candidate,
            "recommendation": record.recommendation,
            "method": record.method,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _record_from_json(value: str) -> ExperienceRecord:
    payload = json.loads(value)
    return ExperienceRecord(
        experience_id=str(payload["experience_id"]),
        verification_id=str(payload["verification_id"]),
        execution_id=str(payload["execution_id"]),
        review_id=str(payload["review_id"]),
        snapshot_digest=str(payload["snapshot_digest"]),
        created_at=_datetime(str(payload["created_at"])),
        outcome=ExperienceOutcome(str(payload["outcome"])),
        summary=str(payload["summary"]),
        lesson_candidates=tuple(
            LessonCandidate(
                category=LessonCategory(str(item["category"])),
                observation=str(item["observation"]),
                lesson=str(item["lesson"]),
                confidence=float(item["confidence"]),
                reusable=bool(item["reusable"]),
                tool_id=item.get("tool_id"),
                operation_id=item.get("operation_id"),
                step_index=item.get("step_index"),
            )
            for item in payload["lesson_candidates"]
        ),
        memory_candidate=bool(payload["memory_candidate"]),
        recommendation=str(payload["recommendation"]),
        method=str(payload["method"]),
    )


def _timestamp(value: datetime) -> str:
    return value.astimezone(UTC).isoformat()


def _datetime(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        raise ValueError("Stored experience timestamp must include a timezone.")
    return parsed.astimezone(UTC)
