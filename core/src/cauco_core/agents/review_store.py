import hashlib
import json
import secrets
from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from threading import RLock
from typing import Any

from cauco_agents import (
    APPROVAL_WARNING,
    AgentContext,
    AgentPlan,
    AgentPlanReviewRecord,
    AgentPlanReviewStatus,
    AgentRouteResult,
)

DEFAULT_PLAN_REVIEW_TTL_SECONDS = 1800
MIN_PLAN_REVIEW_TTL_SECONDS = 60
MAX_PLAN_REVIEW_TTL_SECONDS = 86_400
DEFAULT_MAX_PLAN_REVIEWS = 100
MAX_REVIEWER_NOTE_CHARS = 2000
MAX_REVIEW_REASON_CHARS = 1000


class PlanReviewStoreError(RuntimeError):
    """Base class for safe plan review lifecycle failures."""


class PlanReviewNotFoundError(PlanReviewStoreError):
    pass


class PlanReviewStateConflictError(PlanReviewStoreError):
    pass


class PlanReviewIntegrityError(PlanReviewStoreError):
    pass


class PlanReviewCapacityError(PlanReviewStoreError):
    pass


class AgentPlanReviewStore:
    """Thread-safe process-local storage for immutable reviewed plan snapshots."""

    def __init__(
        self,
        *,
        default_ttl_seconds: int = DEFAULT_PLAN_REVIEW_TTL_SECONDS,
        max_records: int = DEFAULT_MAX_PLAN_REVIEWS,
        clock: Callable[[], datetime] | None = None,
        id_factory: Callable[[], str] | None = None,
    ) -> None:
        validate_ttl(default_ttl_seconds)
        if not 1 <= max_records <= 10_000:
            raise ValueError("Plan review capacity must be between 1 and 10000.")
        self.default_ttl_seconds = default_ttl_seconds
        self.max_records = max_records
        self.clock = clock or (lambda: datetime.now(tz=UTC))
        self.id_factory = id_factory or (lambda: f"planrev_{secrets.token_urlsafe(18)}")
        self._records: dict[str, AgentPlanReviewRecord] = {}
        self._lock = RLock()

    def create(
        self,
        *,
        instruction: str,
        routing: AgentRouteResult,
        context: AgentContext,
        plan: AgentPlan,
        ttl_seconds: int | None = None,
    ) -> AgentPlanReviewRecord:
        ttl = self.default_ttl_seconds if ttl_seconds is None else ttl_seconds
        validate_ttl(ttl)
        with self._lock:
            now = self.clock()
            self._make_room(now)
            review_id = self._new_review_id()
            digest = snapshot_digest(
                instruction=instruction,
                selected_agent_id=plan.agent_id,
                routing=routing,
                context=context,
                plan=plan,
            )
            record = AgentPlanReviewRecord(
                review_id=review_id,
                status=AgentPlanReviewStatus.PENDING_REVIEW,
                created_at=now,
                expires_at=now + timedelta(seconds=ttl),
                updated_at=now,
                instruction=instruction,
                selected_agent_id=plan.agent_id,
                routing=routing,
                context=context,
                plan=plan,
                snapshot_digest=digest,
                metadata={"contract_version": "phase_5c", "ttl_seconds": ttl},
            )
            self._records[review_id] = record
            return self._snapshot(record)

    def get(self, review_id: str) -> AgentPlanReviewRecord:
        with self._lock:
            record = self._record(review_id)
            record = self._expire_if_needed(record, self.clock())
            return self._snapshot(record)

    def list(
        self,
        *,
        status: AgentPlanReviewStatus | None = None,
        agent_id: str | None = None,
        limit: int = 20,
    ) -> tuple[AgentPlanReviewRecord, ...]:
        if not 1 <= limit <= 100:
            raise ValueError("Plan review list limit must be between 1 and 100.")
        with self._lock:
            now = self.clock()
            for record in tuple(self._records.values()):
                self._expire_if_needed(record, now)
            records = (
                record
                for record in self._records.values()
                if (status is None or record.status is status)
                and (agent_id is None or record.selected_agent_id == agent_id)
            )
            ordered = sorted(
                records,
                key=lambda record: (record.created_at, record.review_id),
                reverse=True,
            )
            return tuple(self._snapshot(record) for record in ordered[:limit])

    def approve(
        self, review_id: str, *, reviewer_note: str | None = None
    ) -> AgentPlanReviewRecord:
        return self._transition(
            review_id,
            AgentPlanReviewStatus.APPROVED,
            reviewer_note=reviewer_note,
        )

    def reject(
        self,
        review_id: str,
        *,
        reason: str,
        reviewer_note: str | None = None,
    ) -> AgentPlanReviewRecord:
        normalized_reason = normalize_review_text(
            reason, field_name="Rejection reason", maximum=MAX_REVIEW_REASON_CHARS
        )
        if normalized_reason is None:
            raise ValueError("Rejection reason is required.")
        return self._transition(
            review_id,
            AgentPlanReviewStatus.REJECTED,
            reviewer_note=reviewer_note,
            reason=normalized_reason,
        )

    def cancel(
        self,
        review_id: str,
        *,
        reason: str | None = None,
        reviewer_note: str | None = None,
    ) -> AgentPlanReviewRecord:
        normalized_reason = normalize_review_text(
            reason, field_name="Cancellation reason", maximum=MAX_REVIEW_REASON_CHARS
        )
        return self._transition(
            review_id,
            AgentPlanReviewStatus.CANCELLED,
            reviewer_note=reviewer_note,
            reason=normalized_reason,
        )

    def verify_integrity(self, record: AgentPlanReviewRecord) -> None:
        actual = snapshot_digest(
            instruction=record.instruction,
            selected_agent_id=record.selected_agent_id,
            routing=record.routing,
            context=record.context,
            plan=record.plan,
        )
        if not secrets.compare_digest(record.snapshot_digest, actual):
            raise PlanReviewIntegrityError("The stored plan review snapshot failed verification.")

    def _transition(
        self,
        review_id: str,
        target: AgentPlanReviewStatus,
        *,
        reviewer_note: str | None,
        reason: str | None = None,
    ) -> AgentPlanReviewRecord:
        normalized_note = normalize_review_text(
            reviewer_note, field_name="Reviewer note", maximum=MAX_REVIEWER_NOTE_CHARS
        )
        with self._lock:
            now = self.clock()
            record = self._expire_if_needed(self._record(review_id), now)
            if record.status is not AgentPlanReviewStatus.PENDING_REVIEW:
                raise PlanReviewStateConflictError(
                    f"Plan review is already {record.status.value}."
                )
            self.verify_integrity(record)
            changes: dict[str, Any] = {
                "status": target,
                "updated_at": now,
                "reviewer_note": normalized_note,
            }
            if target is AgentPlanReviewStatus.APPROVED:
                changes.update(
                    approved_at=now,
                    execution_authorized=True,
                    approval_warning=APPROVAL_WARNING,
                )
            elif target is AgentPlanReviewStatus.REJECTED:
                changes.update(rejected_at=now, rejection_reason=reason)
            elif target is AgentPlanReviewStatus.CANCELLED:
                changes.update(cancelled_at=now, cancellation_reason=reason)
            updated = replace(record, **changes)
            self._records[review_id] = updated
            return self._snapshot(updated)

    def _expire_if_needed(
        self, record: AgentPlanReviewRecord, now: datetime
    ) -> AgentPlanReviewRecord:
        if (
            record.status is AgentPlanReviewStatus.PENDING_REVIEW
            and now >= record.expires_at
        ):
            record = replace(
                record,
                status=AgentPlanReviewStatus.EXPIRED,
                updated_at=now,
                expired_at=now,
            )
            self._records[record.review_id] = record
        return record

    def _make_room(self, now: datetime) -> None:
        for record in tuple(self._records.values()):
            self._expire_if_needed(record, now)
        if len(self._records) < self.max_records:
            return
        terminal = sorted(
            (
                record
                for record in self._records.values()
                if record.status is not AgentPlanReviewStatus.PENDING_REVIEW
            ),
            key=lambda record: (record.updated_at, record.created_at, record.review_id),
        )
        for record in terminal:
            del self._records[record.review_id]
            if len(self._records) < self.max_records:
                return
        raise PlanReviewCapacityError(
            "Plan review capacity is full of active pending records."
        )

    def _record(self, review_id: str) -> AgentPlanReviewRecord:
        record = self._records.get(review_id)
        if record is None:
            raise PlanReviewNotFoundError("Plan review not found.")
        return record

    def _new_review_id(self) -> str:
        for _ in range(10):
            review_id = self.id_factory()
            if review_id not in self._records:
                return review_id
        raise PlanReviewCapacityError("A unique plan review identifier could not be created.")

    @staticmethod
    def _snapshot(record: AgentPlanReviewRecord) -> AgentPlanReviewRecord:
        return replace(record, metadata=dict(record.metadata))


def validate_ttl(ttl_seconds: int) -> None:
    if not MIN_PLAN_REVIEW_TTL_SECONDS <= ttl_seconds <= MAX_PLAN_REVIEW_TTL_SECONDS:
        raise ValueError(
            "Plan review TTL must be between "
            f"{MIN_PLAN_REVIEW_TTL_SECONDS} and {MAX_PLAN_REVIEW_TTL_SECONDS} seconds."
        )


def normalize_review_text(
    value: str | None, *, field_name: str, maximum: int
) -> str | None:
    if value is None:
        return None
    normalized = value.replace("\r\n", "\n").replace("\r", "\n").strip()
    if not normalized:
        return None
    if len(normalized) > maximum:
        raise ValueError(f"{field_name} cannot exceed {maximum} characters.")
    return normalized


def snapshot_digest(
    *,
    instruction: str,
    selected_agent_id: str,
    routing: AgentRouteResult,
    context: AgentContext,
    plan: AgentPlan,
) -> str:
    payload = snapshot_payload(
        instruction=instruction,
        selected_agent_id=selected_agent_id,
        routing=routing,
        context=context,
        plan=plan,
    )
    canonical = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def snapshot_payload(
    *,
    instruction: str,
    selected_agent_id: str,
    routing: AgentRouteResult,
    context: AgentContext,
    plan: AgentPlan,
) -> dict[str, Any]:
    return {
        "instruction": instruction,
        "selected_agent_id": selected_agent_id,
        "routing": route_payload(routing),
        "context": context_payload(context),
        "plan": plan_payload(plan),
        "execution_authorized_at_review": False,
        "execution_performed": False,
    }


def route_payload(routing: AgentRouteResult) -> dict[str, Any]:
    def match_payload(match: Any) -> dict[str, Any]:
        return {
            "agent_id": match.agent_id,
            "matched": match.matched,
            "score": match.score,
            "matched_signals": list(match.matched_signals),
            "reasoning": list(match.reasoning),
            "priority": match.priority,
        }

    result = None
    if routing.result is not None:
        result = {
            "agent_id": routing.result.agent_id,
            "agent_name": routing.result.agent_name,
            "status": routing.result.status,
            "summary": routing.result.summary,
            "proposed_actions": list(routing.result.proposed_actions),
            "warnings": list(routing.result.warnings),
            "requires_confirmation": routing.result.requires_confirmation,
            "execution_performed": routing.result.execution_performed,
            "metadata": dict(routing.result.metadata),
        }
    return {
        "request": {
            "instruction": routing.request.instruction,
            "intent": routing.request.intent,
            "context": dict(routing.request.context),
            "preferred_agent_id": routing.request.preferred_agent_id,
            "allow_execution": routing.request.allow_execution,
        },
        "selected_agent_id": routing.selected_agent_id,
        "selected_agent_name": routing.selected_agent_name,
        "match": match_payload(routing.match) if routing.match is not None else None,
        "matches": [match_payload(match) for match in routing.matches],
        "result": result,
        "preferred_agent_rejected": routing.preferred_agent_rejected,
    }


def context_payload(context: AgentContext) -> dict[str, Any]:
    return {
        "agent_id": context.agent_id,
        "instruction": context.instruction,
        "resolved_intent": context.resolved_intent,
        "memory_references": [
            {
                "memory_id": item.memory_id,
                "name": item.name,
                "kind": item.kind,
                "layer": item.layer,
                "title": item.title,
                "relative_path": item.relative_path,
                "reason_selected": item.reason_selected,
                "excerpt": item.excerpt,
                "excerpt_truncated": item.excerpt_truncated,
                "modified_at": item.modified_at,
                "excerpt_strategy": item.excerpt_strategy,
                "selected_headings": list(item.selected_headings),
            }
            for item in context.memory_references
        ],
        "context_summary": context.context_summary,
        "limitations": list(context.limitations),
        "metadata": dict(context.metadata),
    }


def plan_payload(plan: AgentPlan) -> dict[str, Any]:
    return {
        "agent_id": plan.agent_id,
        "agent_name": plan.agent_name,
        "status": plan.status,
        "objective": plan.objective,
        "context_used": plan.context_used,
        "steps": [
            {
                "order": step.order,
                "title": step.title,
                "description": step.description,
                "source_memory_ids": list(step.source_memory_ids),
                "proposed_action": step.proposed_action,
                "requires_confirmation": step.requires_confirmation,
                "execution_available": step.execution_available,
                "warnings": list(step.warnings),
                "tool_reference": (
                    {
                        "tool_id": step.tool_reference.tool_id,
                        "operation_id": step.tool_reference.operation_id,
                        "target": step.tool_reference.target,
                    }
                    if step.tool_reference is not None
                    else None
                ),
            }
            for step in plan.steps
        ],
        "open_questions": list(plan.open_questions),
        "warnings": list(plan.warnings),
        "requires_confirmation": plan.requires_confirmation,
        "execution_performed": plan.execution_performed,
        "metadata": dict(plan.metadata),
    }
