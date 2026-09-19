"""Small persistent store for filesystem-only conversation drafts."""

import hashlib
import json
import os
import secrets
import tempfile
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from threading import Lock
from uuid import UUID


class DraftStatus(StrEnum):
    ACTIVE = "active"
    FINALIZED = "finalized"
    CANCELLED = "cancelled"


class FilesystemDraftError(RuntimeError):
    pass


class DraftNotFoundError(FilesystemDraftError):
    pass


class DraftOwnershipError(FilesystemDraftError):
    pass


class DraftStateError(FilesystemDraftError):
    pass


@dataclass(frozen=True, slots=True)
class FilesystemDraft:
    draft_id: str
    conversation_id: UUID
    target_relative_path: str
    content: str
    digest: str
    status: DraftStatus
    created_at: datetime
    updated_at: datetime


class FilesystemDraftStore:
    """Filesystem draft records, deliberately scoped to one workspace."""

    def __init__(self, workspace: Path, *, clock=None) -> None:
        self.workspace = workspace.resolve(strict=True)
        self.root = self.workspace / "cauco-drafts"
        self.root.mkdir(mode=0o700, exist_ok=True)
        if self.root.is_symlink() or not self.root.is_dir():
            raise ValueError("Filesystem draft staging is unavailable.")
        self.clock = clock or (lambda: datetime.now(UTC))
        self._lock = Lock()

    def create(self, conversation_id: UUID, target_relative_path: str, content: str) -> FilesystemDraft:
        with self._lock:
            if self.get_active_by_conversation(conversation_id) is not None:
                raise DraftStateError("An active filesystem draft already exists for this conversation.")
            now = self.clock()
            draft = FilesystemDraft(
                draft_id="fsdraft_" + secrets.token_urlsafe(18), conversation_id=conversation_id,
                target_relative_path=target_relative_path, content=content, digest=_digest(content),
                status=DraftStatus.ACTIVE, created_at=now, updated_at=now,
            )
            self._write(draft)
            return draft

    def get(self, draft_id: str) -> FilesystemDraft:
        path = self._path(draft_id)
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError as error:
            raise DraftNotFoundError("Filesystem draft not found.") from error
        draft = _from_json(data)
        if _digest(draft.content) != draft.digest:
            raise FilesystemDraftError("Filesystem draft integrity check failed.")
        return draft

    def get_active_by_conversation(self, conversation_id: UUID) -> FilesystemDraft | None:
        for path in sorted(self.root.glob("fsdraft_*.json")):
            draft = self.get(path.stem)
            if draft.conversation_id == conversation_id and draft.status is DraftStatus.ACTIVE:
                return draft
        return None

    def update(self, draft_id: str, conversation_id: UUID, content: str) -> FilesystemDraft:
        draft = self._owned_active(draft_id, conversation_id)
        updated = replace(draft, content=content, digest=_digest(content), updated_at=self.clock())
        with self._lock:
            self._write(updated)
        return updated

    def mark_finalized(self, draft_id: str, conversation_id: UUID) -> FilesystemDraft:
        return self._transition(draft_id, conversation_id, DraftStatus.FINALIZED)

    def cancel(self, draft_id: str, conversation_id: UUID) -> FilesystemDraft:
        return self._transition(draft_id, conversation_id, DraftStatus.CANCELLED)

    def _transition(self, draft_id: str, conversation_id: UUID, status: DraftStatus) -> FilesystemDraft:
        draft = self._owned_active(draft_id, conversation_id)
        updated = replace(draft, status=status, updated_at=self.clock())
        with self._lock:
            self._write(updated)
        return updated

    def _owned_active(self, draft_id: str, conversation_id: UUID) -> FilesystemDraft:
        draft = self.get(draft_id)
        if draft.conversation_id != conversation_id:
            raise DraftOwnershipError("Filesystem draft belongs to another conversation.")
        if draft.status is not DraftStatus.ACTIVE:
            raise DraftStateError("Filesystem draft is no longer active.")
        return draft

    def _path(self, draft_id: str) -> Path:
        if not draft_id.startswith("fsdraft_") or "/" in draft_id or "\\" in draft_id:
            raise DraftNotFoundError("Filesystem draft not found.")
        return self.root / f"{draft_id}.json"

    def _write(self, draft: FilesystemDraft) -> None:
        target = self._path(draft.draft_id)
        raw = json.dumps(_to_json(draft), sort_keys=True, separators=(",", ":")).encode()
        fd, temporary = tempfile.mkstemp(prefix="draft-", suffix=".tmp", dir=self.root)
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(raw); handle.flush(); os.fsync(handle.fileno())
            os.replace(temporary, target)
        finally:
            Path(temporary).unlink(missing_ok=True)


def _digest(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _to_json(draft: FilesystemDraft) -> dict[str, str]:
    return {"draft_id": draft.draft_id, "conversation_id": str(draft.conversation_id), "target_relative_path": draft.target_relative_path, "content": draft.content, "digest": draft.digest, "status": draft.status.value, "created_at": draft.created_at.isoformat(), "updated_at": draft.updated_at.isoformat()}


def _from_json(value: dict[str, str]) -> FilesystemDraft:
    return FilesystemDraft(value["draft_id"], UUID(value["conversation_id"]), value["target_relative_path"], value["content"], value["digest"], DraftStatus(value["status"]), datetime.fromisoformat(value["created_at"]), datetime.fromisoformat(value["updated_at"]))
