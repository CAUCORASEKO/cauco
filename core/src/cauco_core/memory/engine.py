import hashlib
from datetime import UTC, datetime
from pathlib import Path

from cauco_core.memory.classifier import classify_memory, normalized_preview
from cauco_core.memory.exceptions import (
    MemoryDirectoryError,
    MemoryFileNotFoundError,
    MemoryFileTooLargeError,
    MemoryFileUnreadableError,
)
from cauco_core.memory.models import (
    MemoryEngineStatus,
    MemoryFileContent,
    MemoryKind,
    MemoryLayer,
    MemoryObject,
    MemoryRegistrySummary,
)
from cauco_core.memory.registry import MemoryRegistry
from cauco_core.memory.service import MemoryService


class MemoryEngine:
    def __init__(
        self,
        brain_dir: Path | MemoryService,
        max_file_size: int = 524_288,
    ) -> None:
        self.memory_service = (
            brain_dir
            if isinstance(brain_dir, MemoryService)
            else MemoryService(brain_dir, max_file_size=max_file_size)
        )
        self.registry = MemoryRegistry()
        self.refreshed_at: datetime | None = None
        self._status = "not_refreshed"

    def refresh(self) -> MemoryEngineStatus:
        objects: list[MemoryObject] = []
        try:
            discovered_files = self.memory_service.list_markdown_files()
        except MemoryDirectoryError:
            self._status = "unavailable"
            raise
        for metadata in discovered_files:
            try:
                memory_file = self.memory_service.read_file(metadata.relative_path)
            except (
                MemoryFileNotFoundError,
                MemoryFileTooLargeError,
                MemoryFileUnreadableError,
            ):
                continue
            classification = classify_memory(
                memory_file.relative_path,
                memory_file.title,
                memory_file.content,
            )
            objects.append(
                MemoryObject(
                    id=self._stable_id(memory_file.relative_path),
                    name=memory_file.name,
                    kind=classification.kind,
                    layer=classification.layer,
                    path=memory_file.relative_path,
                    relative_path=memory_file.relative_path,
                    title=memory_file.title,
                    content=memory_file.content,
                    preview=normalized_preview(memory_file.content),
                    metadata={
                        "front_matter": classification.front_matter,
                        "headings": classification.headings,
                    },
                    modified_at=memory_file.modified_at,
                    size_bytes=memory_file.size,
                    classification_confidence=classification.confidence,
                    classification_reasons=classification.reasons,
                )
            )
        self.registry.replace(objects)
        self.refreshed_at = datetime.now(tz=UTC)
        self._status = "ready"
        return self.status()

    def list_objects(self) -> list[MemoryObject]:
        return self.registry.list_all()

    def get_object(self, memory_id: str) -> MemoryObject | None:
        return self.registry.get(memory_id)

    def read_object(self, memory_id: str) -> MemoryFileContent | None:
        memory = self.registry.get(memory_id)
        if memory is None:
            return None
        return self.memory_service.read_file(memory.relative_path)

    def get_by_kind(self, kind: MemoryKind) -> list[MemoryObject]:
        return self.registry.get_by_kind(kind)

    def get_by_layer(self, layer: MemoryLayer) -> list[MemoryObject]:
        return self.registry.get_by_layer(layer)

    def summary(self) -> MemoryRegistrySummary:
        return self.registry.summary()

    def status(self) -> MemoryEngineStatus:
        return MemoryEngineStatus(
            status=self._status,
            refreshed_at=self.refreshed_at,
            summary=self.summary(),
        )

    @staticmethod
    def _stable_id(relative_path: str) -> str:
        digest = hashlib.sha256(relative_path.encode("utf-8")).hexdigest()[:20]
        return f"memory_{digest}"
