from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from enum import Enum
from types import MappingProxyType
from typing import Any

from cauco_tools import ToolExecutionResult

from cauco_core.execution.models import (
    AgentPlanExecutionRecord,
    AgentPlanStepExecutionRecord,
    ExecutionAuditEvent,
    ExecutionStatus,
    StepExecutionStatus,
)
from cauco_core.execution.store import ExecutionStore
from cauco_core.persistence import SQLiteDatabase


class SQLiteExecutionStore(ExecutionStore):
    """Persistent execution store backed by Cauco's local SQLite database.

    The existing in-memory store remains the source of domain behavior.
    This subclass restores records at startup and persists every accepted
    state transition atomically without changing the public store contract.
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
        review_id: str,
        snapshot_digest: str,
        steps: tuple[AgentPlanStepExecutionRecord, ...],
    ) -> AgentPlanExecutionRecord:
        with self._lock:
            before_ids = set(self._records)
            record = super().create(review_id, snapshot_digest, steps)
            evicted_ids = before_ids - set(self._records)
            self._persist_record(record, delete_execution_ids=evicted_ids)
            return record

    def append_event(
        self,
        execution_id: str,
        event_type: str,
        outcome: str,
        message: str,
        *,
        step_index: int | None = None,
        tool_id: str | None = None,
        operation_id: str | None = None,
    ) -> AgentPlanExecutionRecord:
        with self._lock:
            record = super().append_event(
                execution_id,
                event_type,
                outcome,
                message,
                step_index=step_index,
                tool_id=tool_id,
                operation_id=operation_id,
            )
            self._persist_record(record)
            return record

    def record_rejected_attempt(self, review_id: str, message: str) -> None:
        with self._lock:
            super().record_rejected_attempt(review_id, message)
            event = self._rejected_events[-1]

            with self.database.transaction() as connection:
                connection.execute(
                    """
                    INSERT INTO rejected_execution_audit_events (
                        event_id,
                        review_id,
                        event_type,
                        timestamp,
                        outcome,
                        safe_message,
                        metadata_json
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        event.event_id,
                        event.review_id,
                        event.event_type,
                        _timestamp(event.timestamp),
                        event.outcome,
                        event.safe_message,
                        _json_dump(event.metadata),
                    ),
                )
                connection.execute(
                    """
                    DELETE FROM rejected_execution_audit_events
                    WHERE event_id IN (
                        SELECT event_id
                        FROM rejected_execution_audit_events
                        ORDER BY timestamp DESC, event_id DESC
                        LIMIT -1 OFFSET 100
                    )
                    """
                )

    def start_step(
        self,
        execution_id: str,
        step_index: int,
    ) -> AgentPlanExecutionRecord:
        with self._lock:
            try:
                record = super().start_step(execution_id, step_index)
            except Exception:
                self._persist_if_present(execution_id)
                raise

            self._persist_record(record)
            return record

    def finish_step(
        self,
        execution_id: str,
        step_index: int,
        *,
        result: ToolExecutionResult | None,
        error: str | None,
        performed: bool,
    ) -> AgentPlanExecutionRecord:
        with self._lock:
            record = super().finish_step(
                execution_id,
                step_index,
                result=result,
                error=error,
                performed=performed,
            )
            self._persist_record(record)
            return record

    def fail_before_start(
        self,
        execution_id: str,
        reason: str,
    ) -> AgentPlanExecutionRecord:
        with self._lock:
            record = super().fail_before_start(execution_id, reason)
            self._persist_record(record)
            return record

    def fail_runtime(
        self,
        execution_id: str,
        reason: str,
    ) -> AgentPlanExecutionRecord:
        with self._lock:
            record = super().fail_runtime(execution_id, reason)
            self._persist_record(record)
            return record

    def retry_step(
        self,
        execution_id: str,
        step_index: int,
    ) -> AgentPlanExecutionRecord:
        with self._lock:
            record = super().retry_step(execution_id, step_index)
            self._persist_record(record)
            return record

    def skip_failed_step(
        self,
        execution_id: str,
        step_index: int,
    ) -> AgentPlanExecutionRecord:
        with self._lock:
            record = super().skip_failed_step(execution_id, step_index)
            self._persist_record(record)
            return record

    def cancel(self, execution_id: str) -> AgentPlanExecutionRecord:
        with self._lock:
            record = super().cancel(execution_id)
            self._persist_record(record)
            return record

    def _restore(self) -> None:
        with self._lock, self.database.connection() as connection:
            execution_rows = connection.execute(
                """
                SELECT *
                FROM executions
                ORDER BY created_at ASC, execution_id ASC
                """
            ).fetchall()

            records: dict[str, AgentPlanExecutionRecord] = {}
            by_review: dict[str, str] = {}

            for execution_row in execution_rows:
                execution_id = str(execution_row["execution_id"])

                step_rows = connection.execute(
                    """
                    SELECT *
                    FROM execution_steps
                    WHERE execution_id = ?
                    ORDER BY step_index ASC
                    """,
                    (execution_id,),
                ).fetchall()

                event_rows = connection.execute(
                    """
                    SELECT *
                    FROM execution_audit_events
                    WHERE execution_id = ?
                    ORDER BY timestamp ASC, event_id ASC
                    """,
                    (execution_id,),
                ).fetchall()

                steps = tuple(_step_from_row(row) for row in step_rows)
                events = tuple(_event_from_row(row) for row in event_rows)

                record = AgentPlanExecutionRecord(
                    execution_id=execution_id,
                    review_id=str(execution_row["review_id"]),
                    snapshot_digest=str(execution_row["snapshot_digest"]),
                    status=ExecutionStatus(str(execution_row["status"])),
                    created_at=_datetime(str(execution_row["created_at"])),
                    started_at=_optional_datetime(execution_row["started_at"]),
                    completed_at=_optional_datetime(execution_row["completed_at"]),
                    current_step_index=(
                        int(execution_row["current_step_index"])
                        if execution_row["current_step_index"] is not None
                        else None
                    ),
                    total_steps=int(execution_row["total_steps"]),
                    step_records=steps,
                    execution_performed=bool(execution_row["execution_performed"]),
                    failure_reason=(
                        str(execution_row["failure_reason"])
                        if execution_row["failure_reason"] is not None
                        else None
                    ),
                    audit_events=events,
                    warning=str(execution_row["warning"]),
                )
                records[execution_id] = record
                by_review[record.review_id] = execution_id

            rejected_rows = connection.execute(
                """
                SELECT *
                FROM rejected_execution_audit_events
                ORDER BY timestamp ASC, event_id ASC
                """
            ).fetchall()

            self._records = records
            self._by_review = by_review
            self._rejected_events = tuple(
                ExecutionAuditEvent(
                    event_id=str(row["event_id"]),
                    event_type=str(row["event_type"]),
                    timestamp=_datetime(str(row["timestamp"])),
                    execution_id=None,
                    review_id=str(row["review_id"]),
                    outcome=str(row["outcome"]),
                    safe_message=str(row["safe_message"]),
                    metadata=_json_load_mapping(str(row["metadata_json"])),
                )
                for row in rejected_rows
            )

    def _persist_if_present(self, execution_id: str) -> None:
        record = self._records.get(execution_id)
        if record is not None:
            self._persist_record(record)

    def _persist_record(
        self,
        record: AgentPlanExecutionRecord,
        *,
        delete_execution_ids: set[str] | None = None,
    ) -> None:
        with self.database.transaction() as connection:
            for execution_id in delete_execution_ids or set():
                connection.execute(
                    "DELETE FROM executions WHERE execution_id = ?",
                    (execution_id,),
                )

            connection.execute(
                """
                INSERT INTO executions (
                    execution_id,
                    review_id,
                    snapshot_digest,
                    status,
                    created_at,
                    started_at,
                    completed_at,
                    current_step_index,
                    total_steps,
                    execution_performed,
                    failure_reason,
                    warning
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(execution_id) DO UPDATE SET
                    review_id = excluded.review_id,
                    snapshot_digest = excluded.snapshot_digest,
                    status = excluded.status,
                    created_at = excluded.created_at,
                    started_at = excluded.started_at,
                    completed_at = excluded.completed_at,
                    current_step_index = excluded.current_step_index,
                    total_steps = excluded.total_steps,
                    execution_performed = excluded.execution_performed,
                    failure_reason = excluded.failure_reason,
                    warning = excluded.warning
                """,
                (
                    record.execution_id,
                    record.review_id,
                    record.snapshot_digest,
                    record.status.value,
                    _timestamp(record.created_at),
                    _optional_timestamp(record.started_at),
                    _optional_timestamp(record.completed_at),
                    record.current_step_index,
                    record.total_steps,
                    int(record.execution_performed),
                    record.failure_reason,
                    record.warning,
                ),
            )

            connection.execute(
                "DELETE FROM execution_steps WHERE execution_id = ?",
                (record.execution_id,),
            )
            connection.execute(
                "DELETE FROM execution_audit_events WHERE execution_id = ?",
                (record.execution_id,),
            )

            connection.executemany(
                """
                INSERT INTO execution_steps (
                    execution_id,
                    step_index,
                    tool_id,
                    operation_id,
                    target,
                    status,
                    started_at,
                    completed_at,
                    result_json,
                    error,
                    execution_performed
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        record.execution_id,
                        step.step_index,
                        step.tool_id,
                        step.operation_id,
                        step.target,
                        step.status.value,
                        _optional_timestamp(step.started_at),
                        _optional_timestamp(step.completed_at),
                        _result_json(step.result),
                        step.error,
                        int(step.execution_performed),
                    )
                    for step in record.step_records
                ],
            )

            connection.executemany(
                """
                INSERT INTO execution_audit_events (
                    event_id,
                    execution_id,
                    review_id,
                    event_type,
                    timestamp,
                    step_index,
                    tool_id,
                    operation_id,
                    outcome,
                    safe_message,
                    metadata_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        event.event_id,
                        event.execution_id,
                        event.review_id,
                        event.event_type,
                        _timestamp(event.timestamp),
                        event.step_index,
                        event.tool_id,
                        event.operation_id,
                        event.outcome,
                        event.safe_message,
                        _json_dump(event.metadata),
                    )
                    for event in record.audit_events
                ],
            )


def _step_from_row(row: Any) -> AgentPlanStepExecutionRecord:
    return AgentPlanStepExecutionRecord(
        step_index=int(row["step_index"]),
        tool_id=str(row["tool_id"]),
        operation_id=str(row["operation_id"]),
        target=str(row["target"]) if row["target"] is not None else None,
        status=StepExecutionStatus(str(row["status"])),
        started_at=_optional_datetime(row["started_at"]),
        completed_at=_optional_datetime(row["completed_at"]),
        result=_result_from_json(row["result_json"]),
        error=str(row["error"]) if row["error"] is not None else None,
        execution_performed=bool(row["execution_performed"]),
    )


def _event_from_row(row: Any) -> ExecutionAuditEvent:
    return ExecutionAuditEvent(
        event_id=str(row["event_id"]),
        event_type=str(row["event_type"]),
        timestamp=_datetime(str(row["timestamp"])),
        execution_id=(str(row["execution_id"]) if row["execution_id"] is not None else None),
        review_id=str(row["review_id"]),
        outcome=str(row["outcome"]),
        safe_message=str(row["safe_message"]),
        step_index=int(row["step_index"]) if row["step_index"] is not None else None,
        tool_id=str(row["tool_id"]) if row["tool_id"] is not None else None,
        operation_id=(str(row["operation_id"]) if row["operation_id"] is not None else None),
        metadata=_json_load_mapping(str(row["metadata_json"])),
    )


def _result_json(result: ToolExecutionResult | None) -> str | None:
    if result is None:
        return None

    return _json_dump(
        {
            "tool_id": result.tool_id,
            "operation_id": result.operation_id,
            "success": result.success,
            "started_at": _timestamp(result.started_at),
            "completed_at": _timestamp(result.completed_at),
            "duration_ms": result.duration_ms,
            "output": result.output,
            "structured_data": _thaw(result.structured_data),
            "error_code": result.error_code,
            "error_message": result.error_message,
            "truncated": result.truncated,
            "execution_performed": result.execution_performed,
            "mutation_performed": result.mutation_performed,
        }
    )


def _result_from_json(value: Any) -> ToolExecutionResult | None:
    if value is None:
        return None

    payload = json.loads(str(value))
    if not isinstance(payload, dict):
        raise ValueError("Stored tool execution result is invalid.")

    structured_data = payload.get("structured_data", {})
    if not isinstance(structured_data, dict):
        raise ValueError("Stored tool execution structured data is invalid.")

    return ToolExecutionResult(
        tool_id=str(payload["tool_id"]),
        operation_id=str(payload["operation_id"]),
        success=bool(payload["success"]),
        started_at=_datetime(str(payload["started_at"])),
        completed_at=_datetime(str(payload["completed_at"])),
        duration_ms=int(payload["duration_ms"]),
        output=str(payload["output"]),
        structured_data=structured_data,
        error_code=(str(payload["error_code"]) if payload.get("error_code") is not None else None),
        error_message=(
            str(payload["error_message"]) if payload.get("error_message") is not None else None
        ),
        truncated=bool(payload.get("truncated", False)),
        execution_performed=bool(payload.get("execution_performed", True)),
        mutation_performed=bool(payload.get("mutation_performed", False)),
    )


def _json_dump(value: Any) -> str:
    return json.dumps(
        _thaw(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _json_load_mapping(value: str) -> Mapping[str, Any]:
    payload = json.loads(value)
    if not isinstance(payload, dict):
        raise ValueError("Stored execution metadata is invalid.")
    return payload


def _thaw(value: Any) -> Any:
    if isinstance(value, (dict, MappingProxyType, Mapping)):
        return {str(key): _thaw(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_thaw(item) for item in value]
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, (str, int, float, bool, type(None))):
        return value
    raise ValueError("Execution persistence data must be JSON-compatible.")


def _timestamp(value: datetime) -> str:
    return value.astimezone(UTC).isoformat()


def _optional_timestamp(value: datetime | None) -> str | None:
    return _timestamp(value) if value is not None else None


def _datetime(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        raise ValueError("Stored execution timestamp must include a timezone.")
    return parsed.astimezone(UTC)


def _optional_datetime(value: Any) -> datetime | None:
    return _datetime(str(value)) if value is not None else None
