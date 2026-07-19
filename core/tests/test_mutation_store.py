from dataclasses import FrozenInstanceError
from datetime import UTC, datetime, timedelta

import pytest

from cauco_core.mutations.models import MutationConflictError, MutationPreviewStatus
from cauco_core.mutations.store import MutationPreviewStore


def fields() -> dict[str, object]:
    return {
        "execution_id": "exec_abcdefghijklmnopqrstuv",
        "review_id": "planrev_abcdefghijklmnopqrstuv",
        "step_index": 1,
        "tool_id": "filesystem",
        "operation_id": "write_text_file",
        "target": "notes.txt",
        "normalized_arguments": {"relative_path": "notes.txt", "content": "inert"},
        "before_state": {"exists": False},
        "proposed_after_state": {"exists": True},
        "diff_preview": "+inert",
        "preview_digest": "a" * 64,
        "confirmation_phrase": "WRITE WORKSPACE FILE",
    }


def test_preview_contract_and_nested_values_are_immutable() -> None:
    preview = MutationPreviewStore().create(**fields())
    with pytest.raises(FrozenInstanceError):
        preview.status = MutationPreviewStatus.CONFIRMED  # type: ignore[misc]
    with pytest.raises(TypeError):
        preview.normalized_arguments["content"] = "changed"  # type: ignore[index]


def test_expired_cancelled_and_consumed_previews_are_single_use() -> None:
    now = datetime(2026, 7, 19, tzinfo=UTC)
    current = now
    store = MutationPreviewStore(clock=lambda: current)
    expired = store.create(**fields())
    current = now + timedelta(minutes=11)
    assert store.get(expired.preview_id).status is MutationPreviewStatus.EXPIRED
    with pytest.raises(MutationConflictError):
        store.claim(expired.preview_id, expired.execution_id, expired.step_index)

    current = now + timedelta(minutes=12)
    cancelled = store.create(**fields())
    store.cancel(cancelled.execution_id, cancelled.step_index)
    with pytest.raises(MutationConflictError):
        store.claim(cancelled.preview_id, cancelled.execution_id, cancelled.step_index)

    current = now + timedelta(minutes=13)
    claimed = store.create(**fields())
    store.claim(claimed.preview_id, claimed.execution_id, claimed.step_index)
    store.consume(claimed.preview_id)
    with pytest.raises(MutationConflictError):
        store.claim(claimed.preview_id, claimed.execution_id, claimed.step_index)


def test_preview_cannot_be_claimed_for_another_execution_or_step() -> None:
    store = MutationPreviewStore()
    preview = store.create(**fields())
    with pytest.raises(MutationConflictError):
        store.claim(preview.preview_id, "exec_other_abcdefghijklmnop", preview.step_index)
    with pytest.raises(MutationConflictError):
        store.claim(preview.preview_id, preview.execution_id, 2)
