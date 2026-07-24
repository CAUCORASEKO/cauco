from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from enum import Enum
from types import MappingProxyType
from typing import Any

from cauco_core.persistence import SQLiteDatabase
from cauco_core.verification.models import (
    StepVerificationResult,
    VerificationOutcome,
    VerificationRecommendation,
    VerificationRecord,
)
from cauco_core.verification.store import VerificationStore


class SQLiteVerificationStore(VerificationStore):
    """Persistent verification store backed by Cauco's SQLite database.

    VerificationStore remains responsible for the domain behavior,
    uniqueness policy, ordering, and bounded capacity. This subclass restores
    records on startup and atomically persists newly accepted records.
    """

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
            previous_records = dict(self._records)
            previous_by_execution = dict(self._by_execution)

            record = super().create(
                execution_id=execution_id,
                review_id=review_id,
                snapshot_digest=snapshot_digest,
                outcome=outcome,
                recommendation=recommendation,
                method=method,
                step_results=step_results,
                evidence_references=evidence_references,
                deviations=deviations,
                unresolved_conditions=unresolved_conditions,
                rollback_available=rollback_available,
            )

            evicted_ids = set(previous_records) - set(self._records)

            try:
                self._persist_record(
                    record,
                    delete_verification_ids=evicted_ids,
                )
            except Exception:
                self._records = previous_records
                self._by_execution = previous_by_execution
                raise

            return record

    def _restore(self) -> None:
        with self._lock, self.database.connection() as connection:
            rows = connection.execute(
                """
                SELECT record_json
                FROM verification_records
                ORDER BY created_at ASC, verification_id ASC
                """
            ).fetchall()

            records: dict[str, VerificationRecord] = {}
            by_execution: dict[str, str] = {}

            for row in rows:
                record = _record_from_json(str(row["record_json"]))
                records[record.verification_id] = record
                by_execution[record.execution_id] = record.verification_id

            self._records = records
            self._by_execution = by_execution

    def _persist_record(
        self,
        record: VerificationRecord,
        *,
        delete_verification_ids: set[str] | None = None,
    ) -> None:
        with self.database.transaction() as connection:
            for verification_id in delete_verification_ids or set():
                connection.execute(
                    """
                    DELETE FROM verification_records
                    WHERE verification_id = ?
                    """,
                    (verification_id,),
                )

            connection.execute(
                """
                INSERT INTO verification_records (
                    verification_id,
                    execution_id,
                    review_id,
                    snapshot_digest,
                    outcome,
                    recommendation,
                    method,
                    created_at,
                    record_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(verification_id) DO UPDATE SET
                    execution_id = excluded.execution_id,
                    review_id = excluded.review_id,
                    snapshot_digest = excluded.snapshot_digest,
                    outcome = excluded.outcome,
                    recommendation = excluded.recommendation,
                    method = excluded.method,
                    created_at = excluded.created_at,
                    record_json = excluded.record_json
                """,
                (
                    record.verification_id,
                    record.execution_id,
                    record.review_id,
                    record.snapshot_digest,
                    record.outcome.value,
                    record.recommendation.value,
                    record.method,
                    _timestamp(record.created_at),
                    _record_json(record),
                ),
            )


def _record_json(record: VerificationRecord) -> str:
    return json.dumps(
        {
            "verification_id": record.verification_id,
            "execution_id": record.execution_id,
            "review_id": record.review_id,
            "snapshot_digest": record.snapshot_digest,
            "created_at": _timestamp(record.created_at),
            "outcome": record.outcome.value,
            "recommendation": record.recommendation.value,
            "method": record.method,
            "step_results": [
                {
                    "step_index": step.step_index,
                    "tool_id": step.tool_id,
                    "operation_id": step.operation_id,
                    "outcome": step.outcome.value,
                    "method": step.method,
                    "expected_conditions": list(step.expected_conditions),
                    "observed_conditions": list(step.observed_conditions),
                    "evidence_references": list(step.evidence_references),
                    "deviations": list(step.deviations),
                    "unresolved_conditions": list(step.unresolved_conditions),
                    "rollback_available": step.rollback_available,
                }
                for step in record.step_results
            ],
            "evidence_references": list(record.evidence_references),
            "deviations": list(record.deviations),
            "unresolved_conditions": list(record.unresolved_conditions),
            "rollback_available": record.rollback_available,
            "metadata": _thaw(record.metadata),
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _record_from_json(value: str) -> VerificationRecord:
    payload = json.loads(value)
    if not isinstance(payload, dict):
        raise ValueError("Stored verification record is invalid.")

    raw_steps = payload.get("step_results")
    if not isinstance(raw_steps, list):
        raise ValueError("Stored verification step results are invalid.")

    metadata = payload.get("metadata", {})
    if not isinstance(metadata, dict):
        raise ValueError("Stored verification metadata is invalid.")

    return VerificationRecord(
        verification_id=str(payload["verification_id"]),
        execution_id=str(payload["execution_id"]),
        review_id=str(payload["review_id"]),
        snapshot_digest=str(payload["snapshot_digest"]),
        created_at=_datetime(str(payload["created_at"])),
        outcome=VerificationOutcome(str(payload["outcome"])),
        recommendation=VerificationRecommendation(str(payload["recommendation"])),
        method=str(payload["method"]),
        step_results=tuple(_step_from_payload(item) for item in raw_steps),
        evidence_references=_string_tuple(payload.get("evidence_references", [])),
        deviations=_string_tuple(payload.get("deviations", [])),
        unresolved_conditions=_string_tuple(payload.get("unresolved_conditions", [])),
        rollback_available=_optional_bool(payload.get("rollback_available")),
        metadata=metadata,
    )


def _step_from_payload(value: Any) -> StepVerificationResult:
    if not isinstance(value, dict):
        raise ValueError("Stored verification step result is invalid.")

    return StepVerificationResult(
        step_index=int(value["step_index"]),
        tool_id=str(value["tool_id"]),
        operation_id=str(value["operation_id"]),
        outcome=VerificationOutcome(str(value["outcome"])),
        method=str(value["method"]),
        expected_conditions=_string_tuple(value.get("expected_conditions", [])),
        observed_conditions=_string_tuple(value.get("observed_conditions", [])),
        evidence_references=_string_tuple(value.get("evidence_references", [])),
        deviations=_string_tuple(value.get("deviations", [])),
        unresolved_conditions=_string_tuple(value.get("unresolved_conditions", [])),
        rollback_available=_optional_bool(value.get("rollback_available")),
    )


def _string_tuple(value: Any) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise ValueError("Stored verification sequence is invalid.")
    return tuple(str(item) for item in value)


def _optional_bool(value: Any) -> bool | None:
    if value is None or isinstance(value, bool):
        return value
    raise ValueError("Stored verification boolean is invalid.")


def _thaw(value: Any) -> Any:
    if isinstance(value, (dict, MappingProxyType, Mapping)):
        return {str(key): _thaw(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_thaw(item) for item in value]
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, (str, int, float, bool, type(None))):
        return value
    raise ValueError("Verification persistence data must be JSON-compatible.")


def _timestamp(value: datetime) -> str:
    return value.astimezone(UTC).isoformat()


def _datetime(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        raise ValueError("Stored verification timestamp must include a timezone.")
    return parsed.astimezone(UTC)
