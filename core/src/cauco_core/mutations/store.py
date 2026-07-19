import secrets
from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from threading import RLock

from cauco_core.mutations.models import (
    MutationCapacityError,
    MutationConflictError,
    MutationNotFoundError,
    MutationPreview,
    MutationPreviewStatus,
)


class MutationPreviewStore:
    def __init__(
        self,
        *,
        ttl_seconds: int = 600,
        max_records: int = 100,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        if not 60 <= ttl_seconds <= 3600 or not 1 <= max_records <= 10_000:
            raise ValueError("Mutation preview limits are invalid.")
        self.ttl = timedelta(seconds=ttl_seconds)
        self.max_records = max_records
        self.clock = clock or (lambda: datetime.now(tz=UTC))
        self._records: dict[str, MutationPreview] = {}
        self._active: dict[tuple[str, int], str] = {}
        self._lock = RLock()

    def create(self, **fields: object) -> MutationPreview:
        execution_id = str(fields["execution_id"])
        step_index = int(fields["step_index"])  # type: ignore[arg-type]
        key = (execution_id, step_index)
        with self._lock:
            existing_id = self._active.get(key)
            if existing_id:
                existing = self._expire(self._records[existing_id])
                if existing.status is MutationPreviewStatus.PENDING_CONFIRMATION:
                    raise MutationConflictError("A pending mutation preview already exists.")
            self._make_room()
            now = self.clock()
            preview = MutationPreview(
                preview_id=f"mutprev_{secrets.token_urlsafe(18)}",
                created_at=now,
                expires_at=now + self.ttl,
                status=MutationPreviewStatus.PENDING_CONFIRMATION,
                **fields,  # type: ignore[arg-type]
            )
            self._records[preview.preview_id] = preview
            self._active[key] = preview.preview_id
            return preview

    def get(self, preview_id: str) -> MutationPreview:
        with self._lock:
            try:
                preview = self._expire(self._records[preview_id])
            except KeyError as error:
                raise MutationNotFoundError("Mutation preview not found.") from error
            return preview

    def active(self, execution_id: str, step_index: int) -> MutationPreview:
        with self._lock:
            preview_id = self._active.get((execution_id, step_index))
            if preview_id is None:
                raise MutationNotFoundError("Mutation preview not found.")
            return self._expire(self._records[preview_id])

    def claim(self, preview_id: str, execution_id: str, step_index: int) -> MutationPreview:
        with self._lock:
            preview = self.get(preview_id)
            if preview.execution_id != execution_id or preview.step_index != step_index:
                raise MutationConflictError("Mutation preview does not belong to this step.")
            if preview.status is MutationPreviewStatus.EXPIRED:
                raise MutationConflictError("Mutation preview has expired.")
            if preview.status is not MutationPreviewStatus.PENDING_CONFIRMATION:
                raise MutationConflictError(f"Mutation preview is already {preview.status.value}.")
            updated = replace(preview, status=MutationPreviewStatus.CONFIRMED)
            self._records[preview_id] = updated
            return updated

    def consume(self, preview_id: str) -> MutationPreview:
        with self._lock:
            preview = self.get(preview_id)
            if preview.status is not MutationPreviewStatus.CONFIRMED:
                raise MutationConflictError("Mutation preview was not claimed.")
            updated = replace(preview, status=MutationPreviewStatus.CONSUMED)
            self._records[preview_id] = updated
            self._active.pop((preview.execution_id, preview.step_index), None)
            return updated

    def cancel(self, execution_id: str, step_index: int) -> MutationPreview:
        with self._lock:
            preview = self.active(execution_id, step_index)
            if preview.status is not MutationPreviewStatus.PENDING_CONFIRMATION:
                raise MutationConflictError("Only a pending mutation preview can be cancelled.")
            updated = replace(preview, status=MutationPreviewStatus.CANCELLED)
            self._records[preview.preview_id] = updated
            self._active.pop((execution_id, step_index), None)
            return updated

    def _expire(self, preview: MutationPreview) -> MutationPreview:
        if (
            preview.status is MutationPreviewStatus.PENDING_CONFIRMATION
            and self.clock() >= preview.expires_at
        ):
            preview = replace(preview, status=MutationPreviewStatus.EXPIRED)
            self._records[preview.preview_id] = preview
            self._active.pop((preview.execution_id, preview.step_index), None)
        return preview

    def _make_room(self) -> None:
        if len(self._records) < self.max_records:
            return
        terminal = sorted(
            (
                item
                for item in self._records.values()
                if item.status
                in {
                    MutationPreviewStatus.EXPIRED,
                    MutationPreviewStatus.CANCELLED,
                    MutationPreviewStatus.CONSUMED,
                }
            ),
            key=lambda item: (item.created_at, item.preview_id),
        )
        if not terminal:
            raise MutationCapacityError("Mutation preview capacity is full.")
        self._records.pop(terminal[0].preview_id)
