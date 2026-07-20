from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from enum import Enum
from types import MappingProxyType
from typing import Any

from cauco_core.mutations.models import MutationPreview, MutationPreviewStatus
from cauco_core.mutations.store import MutationPreviewStore
from cauco_core.persistence import SQLiteDatabase


class SQLiteMutationPreviewStore(MutationPreviewStore):
    """Persistent mutation preview store backed by local SQLite.

    The in-memory store remains responsible for domain behavior. This
    subclass restores previews at startup and persists every accepted state
    transition without changing the public MutationPreviewStore contract.

    Restart policy:
    - pending, unexpired previews remain pending;
    - pending, expired previews become expired;
    - confirmed previews become cancelled because execution may have been
      interrupted after confirmation;
    - terminal previews remain unchanged.
    """

    def __init__(
        self,
        database: SQLiteDatabase,
        *,
        ttl_seconds: int = 600,
        max_records: int = 100,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.database = database
        self.database.initialize()
        super().__init__(
            ttl_seconds=ttl_seconds,
            max_records=max_records,
            clock=clock,
        )
        self._restore()

    def create(self, **fields: object) -> MutationPreview:
        with self._lock:
            before_ids = set(self._records)
            preview = super().create(**fields)
            evicted_ids = before_ids - set(self._records)
            self._persist_preview(
                preview,
                delete_preview_ids=evicted_ids,
            )
            return preview

    def get(self, preview_id: str) -> MutationPreview:
        with self._lock:
            previous = self._records.get(preview_id)
            preview = super().get(preview_id)

            if previous is not None and preview.status is not previous.status:
                self._persist_preview(preview)

            return preview

    def active(self, execution_id: str, step_index: int) -> MutationPreview:
        with self._lock:
            preview_id = self._active.get((execution_id, step_index))
            previous = self._records.get(preview_id) if preview_id is not None else None

            preview = super().active(execution_id, step_index)

            if previous is not None and preview.status is not previous.status:
                self._persist_preview(preview)

            return preview

    def claim(
        self,
        preview_id: str,
        execution_id: str,
        step_index: int,
    ) -> MutationPreview:
        with self._lock:
            preview = super().claim(preview_id, execution_id, step_index)
            self._persist_preview(preview)
            return preview

    def consume(self, preview_id: str) -> MutationPreview:
        with self._lock:
            preview = super().consume(preview_id)
            self._persist_preview(preview)
            return preview

    def cancel(self, execution_id: str, step_index: int) -> MutationPreview:
        with self._lock:
            preview = super().cancel(execution_id, step_index)
            self._persist_preview(preview)
            return preview

    def _restore(self) -> None:
        now = self.clock()
        changed: list[MutationPreview] = []

        with self._lock, self.database.connection() as connection:
            rows = connection.execute(
                """
                SELECT *
                FROM mutation_previews
                ORDER BY created_at ASC, preview_id ASC
                """
            ).fetchall()

            records: dict[str, MutationPreview] = {}
            active: dict[tuple[str, int], str] = {}

            for row in rows:
                stored_status = MutationPreviewStatus(str(row["status"]))
                status = stored_status

                expires_at = _datetime(str(row["expires_at"]))

                if stored_status is MutationPreviewStatus.CONFIRMED:
                    status = MutationPreviewStatus.CANCELLED
                elif (
                    stored_status is MutationPreviewStatus.PENDING_CONFIRMATION
                    and now >= expires_at
                ):
                    status = MutationPreviewStatus.EXPIRED

                preview = MutationPreview(
                    preview_id=str(row["preview_id"]),
                    execution_id=str(row["execution_id"]),
                    review_id=str(row["review_id"]),
                    step_index=int(row["step_index"]),
                    tool_id=str(row["tool_id"]),
                    operation_id=str(row["operation_id"]),
                    target=str(row["target"]) if row["target"] is not None else None,
                    normalized_arguments=_json_load_mapping(str(row["normalized_arguments_json"])),
                    before_state=_json_load_mapping(str(row["before_state_json"])),
                    proposed_after_state=_json_load_mapping(str(row["proposed_after_state_json"])),
                    diff_preview=str(row["diff_preview"]),
                    preview_digest=str(row["preview_digest"]),
                    confirmation_phrase=str(row["confirmation_phrase"]),
                    created_at=_datetime(str(row["created_at"])),
                    expires_at=expires_at,
                    status=status,
                    warning=str(row["warning"]),
                )

                records[preview.preview_id] = preview

                if status is MutationPreviewStatus.PENDING_CONFIRMATION:
                    active[(preview.execution_id, preview.step_index)] = preview.preview_id

                if status is not stored_status:
                    changed.append(preview)

            self._records = records
            self._active = active

        for preview in changed:
            self._persist_preview(preview)

    def _persist_preview(
        self,
        preview: MutationPreview,
        *,
        delete_preview_ids: set[str] | None = None,
    ) -> None:
        with self.database.transaction() as connection:
            for preview_id in delete_preview_ids or set():
                connection.execute(
                    "DELETE FROM mutation_previews WHERE preview_id = ?",
                    (preview_id,),
                )

            connection.execute(
                """
                INSERT INTO mutation_previews (
                    preview_id,
                    execution_id,
                    review_id,
                    step_index,
                    tool_id,
                    operation_id,
                    target,
                    normalized_arguments_json,
                    before_state_json,
                    proposed_after_state_json,
                    diff_preview,
                    preview_digest,
                    confirmation_phrase,
                    created_at,
                    expires_at,
                    status,
                    warning
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(preview_id) DO UPDATE SET
                    execution_id = excluded.execution_id,
                    review_id = excluded.review_id,
                    step_index = excluded.step_index,
                    tool_id = excluded.tool_id,
                    operation_id = excluded.operation_id,
                    target = excluded.target,
                    normalized_arguments_json = excluded.normalized_arguments_json,
                    before_state_json = excluded.before_state_json,
                    proposed_after_state_json = excluded.proposed_after_state_json,
                    diff_preview = excluded.diff_preview,
                    preview_digest = excluded.preview_digest,
                    confirmation_phrase = excluded.confirmation_phrase,
                    created_at = excluded.created_at,
                    expires_at = excluded.expires_at,
                    status = excluded.status,
                    warning = excluded.warning
                """,
                (
                    preview.preview_id,
                    preview.execution_id,
                    preview.review_id,
                    preview.step_index,
                    preview.tool_id,
                    preview.operation_id,
                    preview.target,
                    _json_dump(preview.normalized_arguments),
                    _json_dump(preview.before_state),
                    _json_dump(preview.proposed_after_state),
                    preview.diff_preview,
                    preview.preview_digest,
                    preview.confirmation_phrase,
                    _timestamp(preview.created_at),
                    _timestamp(preview.expires_at),
                    preview.status.value,
                    preview.warning,
                ),
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
        raise ValueError("Stored mutation preview state is invalid.")

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

    raise ValueError("Mutation persistence data must be JSON-compatible.")


def _timestamp(value: datetime) -> str:
    return value.astimezone(UTC).isoformat()


def _datetime(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)

    if parsed.tzinfo is None:
        raise ValueError("Stored mutation preview timestamp must include a timezone.")

    return parsed.astimezone(UTC)
