from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any

from cauco_core.perception import (
    OPERATIONAL_STATE_SOURCE_ID,
    OperationalStatePerceptionSource,
    PerceptionCapability,
    PerceptionModality,
    PerceptionRequest,
    PerceptionSourceStatus,
)


class FakeStore:
    def __init__(self, records: tuple[Any, ...] = ()) -> None:
        self.records = records

    def list(self, *, limit: int = 20, **_: Any) -> tuple[Any, ...]:
        return self.records[:limit]


def review_record(
    *,
    review_id: str = "planrev_abcdefghijklmnopqrst",
    instruction: str = "Inspect repository status",
    status: str = "pending_review",
    updated_at: datetime | None = None,
) -> SimpleNamespace:
    observed_at = updated_at or datetime(2026, 7, 21, 10, 0, tzinfo=UTC)

    return SimpleNamespace(
        review_id=review_id,
        status=SimpleNamespace(value=status),
        created_at=observed_at - timedelta(minutes=1),
        expires_at=observed_at + timedelta(minutes=30),
        updated_at=observed_at,
        instruction=instruction,
        selected_agent_id="operations",
        reviewer_note=None,
        rejection_reason=None,
        cancellation_reason=None,
        execution_authorized=status == "approved",
        execution_performed=False,
    )


def execution_record(
    *,
    execution_id: str = "exec_abcdefghijklmnopqrst",
    status: str = "pending_execution",
    created_at: datetime | None = None,
    failure_reason: str | None = None,
) -> SimpleNamespace:
    observed_at = created_at or datetime(2026, 7, 21, 11, 0, tzinfo=UTC)

    step = SimpleNamespace(
        tool_id="git",
        operation_id="status",
        target=None,
        status=SimpleNamespace(value="pending"),
        error=None,
    )

    event = SimpleNamespace(
        event_type="execution_created",
        outcome="accepted",
        safe_message="Execution record created.",
        tool_id=None,
        operation_id=None,
    )

    return SimpleNamespace(
        execution_id=execution_id,
        review_id="planrev_abcdefghijklmnopqrst",
        status=SimpleNamespace(value=status),
        created_at=observed_at,
        started_at=None,
        completed_at=None,
        current_step_index=None,
        total_steps=1,
        step_records=(step,),
        execution_performed=False,
        failure_reason=failure_reason,
        audit_events=(event,),
    )


def build_source(
    reviews: tuple[Any, ...] = (),
    executions: tuple[Any, ...] = (),
) -> OperationalStatePerceptionSource:
    return OperationalStatePerceptionSource(
        FakeStore(reviews),  # type: ignore[arg-type]
        FakeStore(executions),  # type: ignore[arg-type]
    )


def test_source_exposes_stable_metadata() -> None:
    source = build_source()

    assert source.metadata.source_id == OPERATIONAL_STATE_SOURCE_ID
    assert source.supports(PerceptionCapability.READ)
    assert source.supports(PerceptionCapability.SEARCH)
    assert not source.supports(PerceptionCapability.WATCH)


def test_health_is_available() -> None:
    health = build_source().health()

    assert health.status is PerceptionSourceStatus.AVAILABLE
    assert health.message is not None
    assert "Operational" in health.message


def test_collect_returns_review_and_execution_signals() -> None:
    source = build_source(
        reviews=(review_record(),),
        executions=(execution_record(),),
    )

    batch = source.collect(PerceptionRequest())

    assert batch.source_id == OPERATIONAL_STATE_SOURCE_ID
    assert len(batch.signals) == 2
    assert batch.signals[0].reference == "execution:exec_abcdefghijklmnopqrst"
    assert batch.signals[1].reference == ("plan-review:planrev_abcdefghijklmnopqrst")
    assert all(signal.modality is PerceptionModality.SYSTEM_EVENT for signal in batch.signals)


def test_collect_applies_global_limit() -> None:
    source = build_source(
        reviews=(review_record(),),
        executions=(execution_record(),),
    )

    batch = source.collect(PerceptionRequest(limit=1))

    assert len(batch.signals) == 1
    assert batch.signals[0].metadata["kind"] == "execution"


def test_search_matches_review_instruction() -> None:
    source = build_source(
        reviews=(
            review_record(
                instruction="Inspect the Aurora repository status",
            ),
        ),
    )

    batch = source.collect(PerceptionRequest(query="Aurora repository"))

    assert len(batch.signals) == 1
    assert batch.signals[0].metadata["kind"] == "plan_review"


def test_search_matches_execution_tool_and_operation() -> None:
    source = build_source(executions=(execution_record(),))

    batch = source.collect(PerceptionRequest(query="git status"))

    assert len(batch.signals) == 1
    assert batch.signals[0].metadata["kind"] == "execution"


def test_search_returns_no_unmatched_signals() -> None:
    source = build_source(
        reviews=(review_record(),),
        executions=(execution_record(),),
    )

    batch = source.collect(PerceptionRequest(query="calendar meeting"))

    assert batch.signals == ()


def test_since_filter_excludes_older_records() -> None:
    old_time = datetime(2026, 7, 20, 10, 0, tzinfo=UTC)
    source = build_source(
        reviews=(review_record(updated_at=old_time),),
        executions=(execution_record(created_at=old_time),),
    )

    batch = source.collect(
        PerceptionRequest(
            since=datetime(2026, 7, 21, 10, 0, tzinfo=UTC),
        )
    )

    assert batch.signals == ()


def test_signal_ids_are_stable() -> None:
    source = build_source(
        reviews=(review_record(),),
        executions=(execution_record(),),
    )

    first = source.collect(PerceptionRequest())
    second = source.collect(PerceptionRequest())

    assert tuple(signal.signal_id for signal in first.signals) == tuple(
        signal.signal_id for signal in second.signals
    )
