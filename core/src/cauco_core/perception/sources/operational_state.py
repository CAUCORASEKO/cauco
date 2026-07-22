from datetime import UTC, datetime
from typing import Any

from cauco_agents import AgentPlanReviewRecord

from cauco_core.agents.review_store import AgentPlanReviewStore
from cauco_core.execution import AgentPlanExecutionRecord, ExecutionStore
from cauco_core.perception.models import (
    PerceptionBatch,
    PerceptionCapability,
    PerceptionHealth,
    PerceptionModality,
    PerceptionRequest,
    PerceptionSignal,
    PerceptionSourceMetadata,
    PerceptionSourceStatus,
)
from cauco_core.perception.source import PerceptionSource

OPERATIONAL_STATE_SOURCE_ID = "operational_state"


class OperationalStatePerceptionSource(PerceptionSource):
    """Read-only perception of Cauco's own operational state."""

    def __init__(
        self,
        review_store: AgentPlanReviewStore,
        execution_store: ExecutionStore,
    ) -> None:
        self.review_store = review_store
        self.execution_store = execution_store
        self._metadata = PerceptionSourceMetadata(
            source_id=OPERATIONAL_STATE_SOURCE_ID,
            name="Operational state",
            description=("Read-only perception of plan reviews and execution activity."),
            capabilities=frozenset(
                {
                    PerceptionCapability.READ,
                    PerceptionCapability.SEARCH,
                }
            ),
        )

    @property
    def metadata(self) -> PerceptionSourceMetadata:
        return self._metadata

    def health(self) -> PerceptionHealth:
        return PerceptionHealth(
            source_id=self.metadata.source_id,
            status=PerceptionSourceStatus.AVAILABLE,
            checked_at=datetime.now(UTC),
            message="Operational review and execution stores are available.",
        )

    def collect(self, request: PerceptionRequest) -> PerceptionBatch:
        collected_at = datetime.now(UTC)

        review_signals = tuple(
            self._signal_from_review(record)
            for record in self.review_store.list(limit=request.limit)
            if self._include_review(record, request)
        )
        execution_signals = tuple(
            self._signal_from_execution(record)
            for record in self.execution_store.list(limit=request.limit)
            if self._include_execution(record, request)
        )

        signals = sorted(
            (*review_signals, *execution_signals),
            key=lambda signal: (
                signal.observed_at,
                signal.signal_id,
            ),
            reverse=True,
        )

        return PerceptionBatch(
            source_id=self.metadata.source_id,
            signals=tuple(signals[: request.limit]),
            collected_at=collected_at,
        )

    def _include_review(
        self,
        record: AgentPlanReviewRecord,
        request: PerceptionRequest,
    ) -> bool:
        if request.since is not None and record.updated_at < request.since:
            return False

        if request.query is None:
            return True

        haystack = " ".join(
            (
                record.review_id,
                record.status.value,
                record.instruction,
                record.selected_agent_id,
                record.reviewer_note or "",
                record.rejection_reason or "",
                record.cancellation_reason or "",
            )
        )
        return self._matches_query(haystack, request.query)

    def _include_execution(
        self,
        record: AgentPlanExecutionRecord,
        request: PerceptionRequest,
    ) -> bool:
        observed_at = self._execution_observed_at(record)

        if request.since is not None and observed_at < request.since:
            return False

        if request.query is None:
            return True

        searchable_parts = [
            record.execution_id,
            record.review_id,
            record.status.value,
            record.failure_reason or "",
        ]

        for step in record.step_records:
            searchable_parts.extend(
                (
                    step.tool_id,
                    step.operation_id,
                    step.target or "",
                    step.status.value,
                    step.error or "",
                )
            )

        for event in record.audit_events:
            searchable_parts.extend(
                (
                    event.event_type,
                    event.outcome,
                    event.safe_message,
                    event.tool_id or "",
                    event.operation_id or "",
                )
            )

        return self._matches_query(" ".join(searchable_parts), request.query)

    def _signal_from_review(
        self,
        record: AgentPlanReviewRecord,
    ) -> PerceptionSignal:
        return PerceptionSignal(
            signal_id=f"operational_review_{record.review_id}",
            source_id=self.metadata.source_id,
            modality=PerceptionModality.SYSTEM_EVENT,
            observed_at=record.updated_at,
            title=f"Plan review: {record.status.value}",
            content=record.instruction,
            reference=f"plan-review:{record.review_id}",
            metadata={
                "kind": "plan_review",
                "review_id": record.review_id,
                "status": record.status.value,
                "agent_id": record.selected_agent_id,
                "created_at": record.created_at.isoformat(),
                "updated_at": record.updated_at.isoformat(),
                "expires_at": record.expires_at.isoformat(),
                "execution_authorized": record.execution_authorized,
                "execution_performed": record.execution_performed,
            },
        )

    def _signal_from_execution(
        self,
        record: AgentPlanExecutionRecord,
    ) -> PerceptionSignal:
        content = f"Execution is {record.status.value} with {record.total_steps} planned step(s)."
        if record.failure_reason:
            content = f"{content} Failure: {record.failure_reason}"

        return PerceptionSignal(
            signal_id=f"operational_execution_{record.execution_id}",
            source_id=self.metadata.source_id,
            modality=PerceptionModality.SYSTEM_EVENT,
            observed_at=self._execution_observed_at(record),
            title=f"Execution: {record.status.value}",
            content=content,
            reference=f"execution:{record.execution_id}",
            metadata=self._execution_metadata(record),
        )

    @staticmethod
    def _execution_metadata(
        record: AgentPlanExecutionRecord,
    ) -> dict[str, Any]:
        return {
            "kind": "execution",
            "execution_id": record.execution_id,
            "review_id": record.review_id,
            "status": record.status.value,
            "created_at": record.created_at.isoformat(),
            "started_at": (
                record.started_at.isoformat() if record.started_at is not None else None
            ),
            "completed_at": (
                record.completed_at.isoformat() if record.completed_at is not None else None
            ),
            "current_step_index": record.current_step_index,
            "total_steps": record.total_steps,
            "execution_performed": record.execution_performed,
            "tools": tuple(dict.fromkeys(step.tool_id for step in record.step_records)),
            "operations": tuple(dict.fromkeys(step.operation_id for step in record.step_records)),
        }

    @staticmethod
    def _execution_observed_at(
        record: AgentPlanExecutionRecord,
    ) -> datetime:
        if record.completed_at is not None:
            return record.completed_at
        if record.started_at is not None:
            return record.started_at
        return record.created_at

    @staticmethod
    def _matches_query(haystack: str, query: str) -> bool:
        normalized_haystack = haystack.casefold()
        terms = tuple(term for term in query.casefold().split() if term)
        return all(term in normalized_haystack for term in terms)
