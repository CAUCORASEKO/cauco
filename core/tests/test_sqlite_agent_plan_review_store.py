import sqlite3
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from cauco_agents import AgentPlanReviewStatus
from cauco_core.agents.review_store import (
    PlanReviewIntegrityError,
    PlanReviewStateConflictError,
)
from cauco_core.agents.sqlite_store import SQLiteAgentPlanReviewStore
from cauco_core.persistence import SQLiteDatabase

from test_agent_plan_review_store import MutableClock, create_review, snapshot


def make_store(path: Path, clock=None, **kwargs):
    return SQLiteAgentPlanReviewStore(SQLiteDatabase(path), clock=clock, **kwargs)


@pytest.mark.parametrize("transition", ["approve", "reject", "cancel"])
def test_terminal_states_survive_restart(tmp_path: Path, transition: str) -> None:
    path = tmp_path / "reviews.db"
    store = make_store(path)
    record = create_review(store)
    if transition == "approve":
        updated = store.approve(record.review_id, reviewer_note="approved note")
    elif transition == "reject":
        updated = store.reject(record.review_id, reason="not now", reviewer_note="reject note")
    else:
        updated = store.cancel(record.review_id, reason="user stopped", reviewer_note="cancel note")

    restored = make_store(path).get(record.review_id)
    assert restored == updated
    assert restored.snapshot_digest == record.snapshot_digest


def test_pending_and_expired_reviews_survive_restart(tmp_path: Path) -> None:
    path = tmp_path / "reviews.db"
    now = datetime(2026, 7, 21, tzinfo=UTC)
    clock = MutableClock(now)
    store = make_store(path, clock=clock)
    pending = create_review(store)
    clock.current = pending.expires_at
    expired = make_store(path, clock=clock).get(pending.review_id)
    assert expired.status is AgentPlanReviewStatus.EXPIRED
    assert make_store(path, clock=clock).get(pending.review_id).status is AgentPlanReviewStatus.EXPIRED


def test_lazy_get_and_list_expiration_are_persisted(tmp_path: Path) -> None:
    path = tmp_path / "reviews.db"
    now = datetime(2026, 7, 21, tzinfo=UTC)
    clock = MutableClock(now)
    store = make_store(path, clock=clock)
    first = create_review(store)
    second = create_review(store, "Second plan")
    clock.current = first.expires_at
    assert store.get(first.review_id).status is AgentPlanReviewStatus.EXPIRED
    clock.current = second.expires_at
    assert store.list(status=AgentPlanReviewStatus.EXPIRED)
    restored = make_store(path, clock=clock)
    assert restored.get(first.review_id).status is AgentPlanReviewStatus.EXPIRED
    assert restored.get(second.review_id).status is AgentPlanReviewStatus.EXPIRED


def test_complete_snapshot_and_typed_inputs_survive_restart(tmp_path: Path) -> None:
    path = tmp_path / "reviews.db"
    routing, context, plan = snapshot()
    store = make_store(path)
    created = store.create(instruction=context.instruction, routing=routing, context=context, plan=plan)
    restored = make_store(path).get(created.review_id)
    assert restored.routing == routing
    assert restored.context == context
    assert restored.plan == plan
    assert restored.snapshot_digest == created.snapshot_digest
    make_store(path).verify_integrity(restored)


def test_capacity_evicts_terminal_rows_but_never_pending(tmp_path: Path) -> None:
    path = tmp_path / "reviews.db"
    store = make_store(path, max_records=2)
    first = create_review(store)
    store.cancel(first.review_id, reason="done")
    second = create_review(store, "Second plan")
    third = create_review(store, "Third plan")
    assert store.get(second.review_id).review_id == second.review_id
    with pytest.raises(Exception):
        store.get(first.review_id)
    with SQLiteDatabase(path).connection() as connection:
        assert connection.execute("SELECT 1 FROM agent_plan_reviews WHERE review_id = ?", (first.review_id,)).fetchone() is None
    pending_store = make_store(tmp_path / "pending.db", max_records=1)
    create_review(pending_store)
    with pytest.raises(Exception, match="capacity"):
        create_review(pending_store, "blocked")


def test_malformed_and_tampered_rows_fail_restore(tmp_path: Path) -> None:
    path = tmp_path / "reviews.db"
    store = make_store(path)
    record = create_review(store)
    with SQLiteDatabase(path).transaction() as connection:
        connection.execute("UPDATE agent_plan_reviews SET record_json = ? WHERE review_id = ?", ("{bad", record.review_id))
    with pytest.raises((ValueError, sqlite3.Error)):
        make_store(path)

    store = make_store(tmp_path / "tampered.db")
    record = create_review(store)
    with SQLiteDatabase(tmp_path / "tampered.db").transaction() as connection:
        row = connection.execute("SELECT record_json FROM agent_plan_reviews WHERE review_id = ?", (record.review_id,)).fetchone()
        connection.execute("UPDATE agent_plan_reviews SET record_json = REPLACE(?, ?, ?) WHERE review_id = ?", (row["record_json"], record.snapshot_digest, "0" * 64, record.review_id))
    with pytest.raises(PlanReviewIntegrityError):
        make_store(tmp_path / "tampered.db")


def test_concurrent_terminal_transitions_have_one_success(tmp_path: Path) -> None:
    store = make_store(tmp_path / "reviews.db")
    record = create_review(store)
    def approve():
        try:
            store.approve(record.review_id)
            return True
        except PlanReviewStateConflictError:
            return False
    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: approve(), range(2)))
    assert sum(results) == 1
