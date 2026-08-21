from __future__ import annotations

import json
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from cauco_agents import (
    AgentContext,
    AgentMatch,
    AgentMemoryReference,
    AgentPlan,
    AgentPlanReviewRecord,
    AgentPlanReviewStatus,
    AgentPlanStep,
    AgentRequest,
    AgentResult,
    AgentRouteResult,
    AgentToolReference,
    CalendarCreateEventInput,
    CalendarListEventsInput,
    EmailDraftInput,
    EmailListAccountsInput,
    EmailListMailboxesInput,
    EmailListMessagesInput,
    FilesystemWriteTextInput,
    MemoryConfirmProposalInput,
    MemoryCreateProposalInput,
    decode_step_output_bindings,
    encode_step_output_bindings,
)
from cauco_tools import GitAddInput, GitCommitInput, GitPushInput

from cauco_core.agents.review_store import AgentPlanReviewStore, PlanReviewIntegrityError
from cauco_core.persistence import SQLiteDatabase

CONTRACT_VERSION = "phase_8d_v1"


class SQLiteAgentPlanReviewStore(AgentPlanReviewStore):
    def __init__(self, database: SQLiteDatabase, **kwargs: Any) -> None:
        self.database = database
        self.restore_skipped_count = 0
        self.database.initialize()
        super().__init__(**kwargs)
        self._restore()

    def create(self, **kwargs: Any) -> AgentPlanReviewRecord:
        with self._lock:
            before = set(self._records)
            record = super().create(**kwargs)
            self._save(record, set(self._records) ^ before)
            return record

    def get(self, review_id: str) -> AgentPlanReviewRecord:
        with self._lock:
            before = self._records.get(review_id)
            record = super().get(review_id)
            if before != self._records.get(review_id):
                self._save(record)
            return record

    def list(self, **kwargs: Any) -> tuple[AgentPlanReviewRecord, ...]:
        with self._lock:
            before = dict(self._records)
            records = super().list(**kwargs)
            for review_id, record in self._records.items():
                if before.get(review_id) != record:
                    self._save(record)
            return records

    def approve(self, review_id: str, *, reviewer_note: str | None = None) -> AgentPlanReviewRecord:
        return self._persist_transition(super().approve, review_id, reviewer_note=reviewer_note)

    def reject(
        self, review_id: str, *, reason: str, reviewer_note: str | None = None
    ) -> AgentPlanReviewRecord:
        return self._persist_transition(
            super().reject, review_id, reason=reason, reviewer_note=reviewer_note
        )

    def cancel(
        self, review_id: str, *, reason: str | None = None, reviewer_note: str | None = None
    ) -> AgentPlanReviewRecord:
        return self._persist_transition(
            super().cancel, review_id, reason=reason, reviewer_note=reviewer_note
        )

    def _persist_transition(
        self, operation: Callable[..., AgentPlanReviewRecord], review_id: str, **kwargs: Any
    ) -> AgentPlanReviewRecord:
        with self._lock:
            record = operation(review_id, **kwargs)
            self._save(record)
            return record

    def _restore(self) -> None:
        normalized: list[AgentPlanReviewRecord] = []
        with self._lock, self.database.connection() as connection:
            rows = connection.execute(
                "SELECT * FROM agent_plan_reviews ORDER BY created_at ASC, review_id ASC"
            ).fetchall()
            for row in rows:
                try:
                    record = _from_json(str(row["record_json"]))
                    self.verify_integrity(record)
                    if (
                        record.review_id,
                        record.status.value,
                        record.selected_agent_id,
                        record.snapshot_digest,
                        _dt(record.created_at),
                        _dt(record.expires_at),
                        _dt(record.updated_at),
                    ) != (
                        row["review_id"],
                        row["status"],
                        row["selected_agent_id"],
                        row["snapshot_digest"],
                        row["created_at"],
                        row["expires_at"],
                        row["updated_at"],
                    ):
                        raise ValueError("Stored plan review index fields are inconsistent.")
                except (ValueError, TypeError, KeyError, PlanReviewIntegrityError):
                    self.restore_skipped_count = min(self.restore_skipped_count + 1, 10_000)
                    continue
                self._records[record.review_id] = record
            now = self.clock()
            for record in tuple(self._records.values()):
                expired = self._expire_if_needed(record, now)
                if expired != record:
                    normalized.append(expired)
        for record in normalized:
            self._save(record)

    def _save(self, record: AgentPlanReviewRecord, deleted: set[str] | None = None) -> None:
        payload = _to_json(record)
        with self.database.transaction() as connection:
            if deleted:
                connection.executemany(
                    "DELETE FROM agent_plan_reviews WHERE review_id = ?",
                    ((item,) for item in deleted),
                )
            connection.execute(
                """
                INSERT INTO agent_plan_reviews (
                    review_id,
                    record_json,
                    status,
                    selected_agent_id,
                    snapshot_digest,
                    created_at,
                    expires_at,
                    updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(review_id) DO UPDATE SET
                    record_json = excluded.record_json,
                    status = excluded.status,
                    selected_agent_id = excluded.selected_agent_id,
                    snapshot_digest = excluded.snapshot_digest,
                    created_at = excluded.created_at,
                    expires_at = excluded.expires_at,
                    updated_at = excluded.updated_at
                """,
                (
                    record.review_id,
                    payload,
                    record.status.value,
                    record.selected_agent_id,
                    record.snapshot_digest,
                    _dt(record.created_at),
                    _dt(record.expires_at),
                    _dt(record.updated_at),
                ),
            )


def _dt(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("Persisted datetimes must be timezone-aware.")
    return value.astimezone(UTC).isoformat()


def _parse_dt(value: Any) -> datetime:
    parsed = datetime.fromisoformat(str(value))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("Stored datetime is not timezone-aware.")
    return parsed.astimezone(UTC)


def _to_json(record: AgentPlanReviewRecord) -> str:
    payload = {"contract_version": CONTRACT_VERSION, "record": _record_payload(record)}
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _record_payload(r: AgentPlanReviewRecord) -> dict[str, Any]:
    return {
        "review_id": r.review_id,
        "status": r.status.value,
        "created_at": _dt(r.created_at),
        "expires_at": _dt(r.expires_at),
        "updated_at": _dt(r.updated_at),
        "instruction": r.instruction,
        "selected_agent_id": r.selected_agent_id,
        "routing": _route(r.routing),
        "context": _context(r.context),
        "plan": _plan(r.plan),
        "snapshot_digest": r.snapshot_digest,
        "execution_authorized": r.execution_authorized,
        "execution_performed": r.execution_performed,
        "approved_at": _optional_dt(r.approved_at),
        "rejected_at": _optional_dt(r.rejected_at),
        "cancelled_at": _optional_dt(r.cancelled_at),
        "expired_at": _optional_dt(r.expired_at),
        "reviewer_note": r.reviewer_note,
        "rejection_reason": r.rejection_reason,
        "cancellation_reason": r.cancellation_reason,
        "approval_warning": r.approval_warning,
        "metadata": dict(r.metadata),
    }


def _optional_dt(v: datetime | None) -> str | None:
    return _dt(v) if v else None


def _match(m: AgentMatch) -> dict[str, Any]:
    return {
        "agent_id": m.agent_id,
        "matched": m.matched,
        "score": m.score,
        "matched_signals": list(m.matched_signals),
        "reasoning": list(m.reasoning),
        "priority": m.priority,
    }


def _request(q: AgentRequest) -> dict[str, Any]:
    return {
        "instruction": q.instruction,
        "intent": q.intent,
        "context": dict(q.context),
        "preferred_agent_id": q.preferred_agent_id,
        "allow_execution": q.allow_execution,
    }


def _result(x: AgentResult | None) -> dict[str, Any] | None:
    return (
        None
        if x is None
        else {
            "agent_id": x.agent_id,
            "agent_name": x.agent_name,
            "status": x.status,
            "summary": x.summary,
            "proposed_actions": list(x.proposed_actions),
            "warnings": list(x.warnings),
            "requires_confirmation": x.requires_confirmation,
            "execution_performed": x.execution_performed,
            "metadata": dict(x.metadata),
        }
    )


def _route(x: AgentRouteResult) -> dict[str, Any]:
    return {
        "request": _request(x.request),
        "selected_agent_id": x.selected_agent_id,
        "selected_agent_name": x.selected_agent_name,
        "match": _match(x.match) if x.match else None,
        "matches": [_match(m) for m in x.matches],
        "result": _result(x.result),
        "preferred_agent_rejected": x.preferred_agent_rejected,
    }


def _context(x: AgentContext) -> dict[str, Any]:
    return {
        "agent_id": x.agent_id,
        "instruction": x.instruction,
        "resolved_intent": x.resolved_intent,
        "memory_references": [
            {
                k: getattr(m, k)
                for k in (
                    "memory_id",
                    "name",
                    "kind",
                    "layer",
                    "title",
                    "relative_path",
                    "reason_selected",
                    "excerpt",
                    "excerpt_truncated",
                    "modified_at",
                    "excerpt_strategy",
                    "selected_headings",
                )
            }
            for m in x.memory_references
        ],
        "context_summary": x.context_summary,
        "limitations": list(x.limitations),
        "metadata": dict(x.metadata),
        "learning_guidance": [dict(item) for item in x.learning_guidance],
    }


def _plan(x: AgentPlan) -> dict[str, Any]:
    return {
        "agent_id": x.agent_id,
        "agent_name": x.agent_name,
        "status": x.status,
        "objective": x.objective,
        "context_used": x.context_used,
        "steps": [
            {
                "order": s.order,
                "title": s.title,
                "description": s.description,
                "source_memory_ids": list(s.source_memory_ids),
                "proposed_action": s.proposed_action,
                "requires_confirmation": s.requires_confirmation,
                "execution_available": s.execution_available,
                "warnings": list(s.warnings),
                "tool_reference": {
                    "tool_id": s.tool_reference.tool_id,
                    "operation_id": s.tool_reference.operation_id,
                    "target": s.tool_reference.target,
                }
                if s.tool_reference
                else None,
                "operation_input": _input(s.operation_input),
            }
            for s in x.steps
        ],
        "open_questions": list(x.open_questions),
        "warnings": list(x.warnings),
        "requires_confirmation": x.requires_confirmation,
        "execution_performed": x.execution_performed,
        "metadata": dict(x.metadata),
    }


def _input(x: Any) -> dict[str, Any] | None:
    if x is None:
        return None
    return (
        {
            "type": type(x).__name__,
            **{k: list(v) if isinstance(v, tuple) else v for k, v in x.__dict__.items()},
        }
        if hasattr(x, "__dict__")
        else {
            "type": type(x).__name__,
            **{k: encode_step_output_bindings(getattr(x, k)) for k in x.__dataclass_fields__},
        }
    )


def _from_json(raw: str) -> AgentPlanReviewRecord:
    data = json.loads(raw)
    if data.get("contract_version") != CONTRACT_VERSION or not isinstance(data.get("record"), dict):
        raise ValueError("Unknown plan review contract.")
    r = data["record"]
    q = r["routing"]["request"]
    request = AgentRequest(**q)

    def match(v):
        if not v:
            return None
        return AgentMatch(
            **{
                **v,
                "matched_signals": tuple(v["matched_signals"]),
                "reasoning": tuple(v["reasoning"]),
            }
        )

    routing = r["routing"]
    result_data = routing["result"]
    result = None
    if result_data:
        result = AgentResult(
            **{
                **result_data,
                "proposed_actions": tuple(result_data["proposed_actions"]),
                "warnings": tuple(result_data["warnings"]),
            }
        )
    route = AgentRouteResult(
        request=request,
        selected_agent_id=routing["selected_agent_id"],
        selected_agent_name=routing["selected_agent_name"],
        match=match(routing["match"]),
        matches=tuple(match(v) for v in routing["matches"]),
        result=result,
        preferred_agent_rejected=routing["preferred_agent_rejected"],
    )
    c = r["context"]
    context = AgentContext(
        **{
            **c,
            "memory_references": tuple(AgentMemoryReference(**m) for m in c["memory_references"]),
            "limitations": tuple(c["limitations"]),
        }
    )
    p = r["plan"]
    steps = []
    classes = {
        "MemoryCreateProposalInput": MemoryCreateProposalInput,
        "MemoryConfirmProposalInput": MemoryConfirmProposalInput,
        "FilesystemWriteTextInput": FilesystemWriteTextInput,
        "GitAddInput": GitAddInput,
        "GitCommitInput": GitCommitInput,
        "GitPushInput": GitPushInput,
        "CalendarListEventsInput": CalendarListEventsInput,
        "CalendarCreateEventInput": CalendarCreateEventInput,
        "EmailDraftInput": EmailDraftInput,
        "EmailListAccountsInput": EmailListAccountsInput,
        "EmailListMailboxesInput": EmailListMailboxesInput,
        "EmailListMessagesInput": EmailListMessagesInput,
    }
    for s in p["steps"]:
        ref = AgentToolReference(**s["tool_reference"]) if s["tool_reference"] else None
        value = s["operation_input"]
        operation = (
            classes[value.pop("type")](
                **{key: decode_step_output_bindings(item) for key, item in value.items()}
            )
            if value
            else None
        )
        steps.append(
            AgentPlanStep(
                **{
                    **s,
                    "source_memory_ids": tuple(s["source_memory_ids"]),
                    "warnings": tuple(s["warnings"]),
                    "tool_reference": ref,
                    "operation_input": operation,
                }
            )
        )
    plan = AgentPlan(
        **{
            **p,
            "steps": tuple(steps),
            "open_questions": tuple(p["open_questions"]),
            "warnings": tuple(p["warnings"]),
        }
    )
    return AgentPlanReviewRecord(
        **{
            **r,
            "status": AgentPlanReviewStatus(r["status"]),
            "created_at": _parse_dt(r["created_at"]),
            "expires_at": _parse_dt(r["expires_at"]),
            "updated_at": _parse_dt(r["updated_at"]),
            "approved_at": _parse_dt(r["approved_at"]) if r["approved_at"] else None,
            "rejected_at": _parse_dt(r["rejected_at"]) if r["rejected_at"] else None,
            "cancelled_at": _parse_dt(r["cancelled_at"]) if r["cancelled_at"] else None,
            "expired_at": _parse_dt(r["expired_at"]) if r["expired_at"] else None,
            "routing": route,
            "context": context,
            "plan": plan,
        }
    )
