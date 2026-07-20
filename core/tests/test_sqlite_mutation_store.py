from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from cauco_core.mutations.models import (
    MutationConflictError,
    MutationNotFoundError,
    MutationPreviewStatus,
)
from cauco_core.mutations.sqlite_store import SQLiteMutationPreviewStore
from cauco_core.persistence import SQLiteDatabase

EXECUTION_ID = "exec_abcdefghijklmnopqrstuv"
REVIEW_ID = "planrev_abcdefghijklmnopqrstuv"


def fields(*, step_index: int = 1) -> dict[str, object]:
    return {
        "execution_id": EXECUTION_ID,
        "review_id": REVIEW_ID,
        "step_index": step_index,
        "tool_id": "filesystem",
        "operation_id": "write_text_file",
        "target": "notes.txt",
        "normalized_arguments": {
            "relative_path": "notes.txt",
            "content": "persistent",
            "lines": ["one", "two"],
        },
        "before_state": {
            "exists": False,
            "metadata": {"kind": "text"},
        },
        "proposed_after_state": {
            "exists": True,
            "nested": {"values": [1, 2, 3]},
        },
        "diff_preview": "+persistent",
        "preview_digest": "a" * 64,
        "confirmation_phrase": "WRITE WORKSPACE FILE",
    }


def database(tmp_path: Path) -> SQLiteDatabase:
    db = SQLiteDatabase(tmp_path / "runtime" / "cauco.db")
    db.initialize()

    with db.transaction() as connection:
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
            """,
            (
                EXECUTION_ID,
                REVIEW_ID,
                "b" * 64,
                "pending_execution",
                datetime(2026, 7, 20, tzinfo=UTC).isoformat(),
                None,
                None,
                None,
                3,
                0,
                None,
                "Execution is controlled and auditable.",
            ),
        )

    return db


def test_created_preview_is_restored_with_nested_state(tmp_path: Path) -> None:
    db = database(tmp_path)
    first = SQLiteMutationPreviewStore(db)

    created = first.create(**fields())

    second = SQLiteMutationPreviewStore(db)
    restored = second.get(created.preview_id)

    assert restored == created
    assert restored.status is MutationPreviewStatus.PENDING_CONFIRMATION
    assert restored.normalized_arguments["lines"] == ("one", "two")
    assert restored.proposed_after_state["nested"]["values"] == (1, 2, 3)
    assert second.active(EXECUTION_ID, 1).preview_id == created.preview_id


def test_claim_is_persisted_and_invalidated_after_restart(tmp_path: Path) -> None:
    db = database(tmp_path)
    first = SQLiteMutationPreviewStore(db)

    created = first.create(**fields())
    claimed = first.claim(created.preview_id, EXECUTION_ID, 1)

    assert claimed.status is MutationPreviewStatus.CONFIRMED

    second = SQLiteMutationPreviewStore(db)
    restored = second.get(created.preview_id)

    assert restored.status is MutationPreviewStatus.CANCELLED

    with pytest.raises(MutationNotFoundError):
        second.active(EXECUTION_ID, 1)

    with pytest.raises(MutationConflictError):
        second.claim(created.preview_id, EXECUTION_ID, 1)


def test_consumed_preview_remains_consumed_after_restart(tmp_path: Path) -> None:
    db = database(tmp_path)
    first = SQLiteMutationPreviewStore(db)

    created = first.create(**fields())
    first.claim(created.preview_id, EXECUTION_ID, 1)
    consumed = first.consume(created.preview_id)

    assert consumed.status is MutationPreviewStatus.CONSUMED

    second = SQLiteMutationPreviewStore(db)
    restored = second.get(created.preview_id)

    assert restored.status is MutationPreviewStatus.CONSUMED

    with pytest.raises(MutationNotFoundError):
        second.active(EXECUTION_ID, 1)


def test_cancelled_preview_remains_cancelled_after_restart(tmp_path: Path) -> None:
    db = database(tmp_path)
    first = SQLiteMutationPreviewStore(db)

    created = first.create(**fields())
    cancelled = first.cancel(EXECUTION_ID, 1)

    assert cancelled.status is MutationPreviewStatus.CANCELLED

    second = SQLiteMutationPreviewStore(db)

    assert second.get(created.preview_id).status is MutationPreviewStatus.CANCELLED


def test_pending_preview_expires_and_persists_expiration(tmp_path: Path) -> None:
    db = database(tmp_path)
    now = datetime(2026, 7, 20, 12, 0, tzinfo=UTC)
    current = now

    first = SQLiteMutationPreviewStore(
        db,
        ttl_seconds=600,
        clock=lambda: current,
    )
    created = first.create(**fields())

    current = now + timedelta(minutes=11)

    assert first.get(created.preview_id).status is MutationPreviewStatus.EXPIRED

    second = SQLiteMutationPreviewStore(
        db,
        ttl_seconds=600,
        clock=lambda: current,
    )

    assert second.get(created.preview_id).status is MutationPreviewStatus.EXPIRED


def test_expired_preview_is_normalized_during_restart(tmp_path: Path) -> None:
    db = database(tmp_path)
    now = datetime(2026, 7, 20, 12, 0, tzinfo=UTC)

    first = SQLiteMutationPreviewStore(
        db,
        ttl_seconds=600,
        clock=lambda: now,
    )
    created = first.create(**fields())

    later = now + timedelta(minutes=11)
    second = SQLiteMutationPreviewStore(
        db,
        ttl_seconds=600,
        clock=lambda: later,
    )

    assert second.get(created.preview_id).status is MutationPreviewStatus.EXPIRED

    third = SQLiteMutationPreviewStore(
        db,
        ttl_seconds=600,
        clock=lambda: later,
    )

    assert third.get(created.preview_id).status is MutationPreviewStatus.EXPIRED


def test_active_pending_preview_conflict_survives_restart(tmp_path: Path) -> None:
    db = database(tmp_path)
    first = SQLiteMutationPreviewStore(db)
    first.create(**fields())

    second = SQLiteMutationPreviewStore(db)

    with pytest.raises(MutationConflictError):
        second.create(**fields())


def test_capacity_eviction_is_deleted_from_sqlite(tmp_path: Path) -> None:
    db = database(tmp_path)
    first = SQLiteMutationPreviewStore(db, max_records=1)

    old = first.create(**fields(step_index=1))
    first.cancel(EXECUTION_ID, 1)

    new = first.create(**fields(step_index=2))

    with pytest.raises(MutationNotFoundError):
        first.get(old.preview_id)

    second = SQLiteMutationPreviewStore(db, max_records=1)

    with pytest.raises(MutationNotFoundError):
        second.get(old.preview_id)

    assert second.get(new.preview_id).preview_id == new.preview_id
