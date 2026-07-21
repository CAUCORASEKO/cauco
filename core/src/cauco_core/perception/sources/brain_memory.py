import hashlib
from datetime import UTC, datetime

from cauco_core.memory.engine import MemoryEngine
from cauco_core.memory.exceptions import InvalidSearchQueryError, MemoryDirectoryError
from cauco_core.memory.models import MemoryObject, MemorySearchResult
from cauco_core.memory.search import MAX_SEARCH_LIMIT, MemorySearch
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

BRAIN_MEMORY_SOURCE_ID = "brain_memory"


class BrainMemoryPerceptionSource(PerceptionSource):
    def __init__(
        self,
        memory_engine: MemoryEngine,
        memory_search: MemorySearch,
    ) -> None:
        self.memory_engine = memory_engine
        self.memory_search = memory_search
        self._metadata = PerceptionSourceMetadata(
            source_id=BRAIN_MEMORY_SOURCE_ID,
            name="Brain memory",
            description="Read-only perception of Cauco's persistent local memory.",
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
        checked_at = datetime.now(UTC)
        engine_status = self.memory_engine.status()

        if engine_status.status == "ready":
            return PerceptionHealth(
                source_id=self.metadata.source_id,
                status=PerceptionSourceStatus.AVAILABLE,
                checked_at=checked_at,
                message=f"{engine_status.summary.total} memory objects available.",
            )

        if engine_status.status == "unavailable":
            return PerceptionHealth(
                source_id=self.metadata.source_id,
                status=PerceptionSourceStatus.UNAVAILABLE,
                checked_at=checked_at,
                message="The configured brain memory is unavailable.",
            )

        return PerceptionHealth(
            source_id=self.metadata.source_id,
            status=PerceptionSourceStatus.DEGRADED,
            checked_at=checked_at,
            message="Brain memory has not been refreshed.",
        )

    def collect(self, request: PerceptionRequest) -> PerceptionBatch:
        if self.memory_engine.status().status != "ready":
            raise RuntimeError("Brain memory must be refreshed before perception.")

        collected_at = datetime.now(UTC)

        if request.query is not None:
            signals = self._search_signals(request, collected_at)
        else:
            signals = self._read_signals(request, collected_at)

        return PerceptionBatch(
            source_id=self.metadata.source_id,
            signals=signals,
            collected_at=collected_at,
        )

    def _read_signals(
        self,
        request: PerceptionRequest,
        collected_at: datetime,
    ) -> tuple[PerceptionSignal, ...]:
        objects = (
            memory
            for memory in self.memory_engine.list_objects()
            if request.since is None
            or memory.modified_at is None
            or memory.modified_at >= request.since
        )
        selected = tuple(objects)[: request.limit]

        return tuple(
            self._signal_from_memory(memory, collected_at)
            for memory in selected
        )

    def _search_signals(
        self,
        request: PerceptionRequest,
        collected_at: datetime,
    ) -> tuple[PerceptionSignal, ...]:
        if request.query is None:
            return ()

        search_limit = min(request.limit, MAX_SEARCH_LIMIT)

        try:
            results = self.memory_search.search(
                request.query,
                limit=search_limit,
            )
        except (InvalidSearchQueryError, MemoryDirectoryError) as error:
            raise ValueError(str(error)) from error

        objects_by_path = {
            memory.relative_path: memory
            for memory in self.memory_engine.list_objects()
        }

        signals: list[PerceptionSignal] = []
        for result in results:
            memory = objects_by_path.get(result.relative_path)

            if (
                request.since is not None
                and memory is not None
                and memory.modified_at is not None
                and memory.modified_at < request.since
            ):
                continue

            signals.append(
                self._signal_from_search_result(
                    result,
                    memory,
                    collected_at,
                )
            )

        return tuple(signals)

    def _signal_from_memory(
        self,
        memory: MemoryObject,
        collected_at: datetime,
    ) -> PerceptionSignal:
        return PerceptionSignal(
            signal_id=self._stable_signal_id(memory.relative_path),
            source_id=self.metadata.source_id,
            modality=PerceptionModality.FILE,
            observed_at=memory.modified_at or collected_at,
            title=memory.title,
            content=memory.preview,
            reference=memory.relative_path,
            confidence=memory.classification_confidence,
            metadata={
                "memory_id": memory.id,
                "relative_path": memory.relative_path,
                "kind": memory.kind.value,
                "layer": memory.layer.value,
                "size_bytes": memory.size_bytes,
                "classification_reasons": memory.classification_reasons,
            },
        )

    def _signal_from_search_result(
        self,
        result: MemorySearchResult,
        memory: MemoryObject | None,
        collected_at: datetime,
    ) -> PerceptionSignal:
        metadata: dict[str, object] = {
            "relative_path": result.relative_path,
            "score": result.score,
            "matched_terms": result.matched_terms,
        }

        confidence = 1.0
        observed_at = collected_at

        if memory is not None:
            metadata.update(
                {
                    "memory_id": memory.id,
                    "kind": memory.kind.value,
                    "layer": memory.layer.value,
                    "size_bytes": memory.size_bytes,
                    "classification_reasons": memory.classification_reasons,
                }
            )
            confidence = memory.classification_confidence
            observed_at = memory.modified_at or collected_at

        return PerceptionSignal(
            signal_id=self._stable_signal_id(result.relative_path),
            source_id=self.metadata.source_id,
            modality=PerceptionModality.FILE,
            observed_at=observed_at,
            title=result.title,
            content=result.excerpt,
            reference=result.relative_path,
            confidence=confidence,
            metadata=metadata,
        )

    @staticmethod
    def _stable_signal_id(relative_path: str) -> str:
        digest = hashlib.sha256(relative_path.encode("utf-8")).hexdigest()[:20]
        return f"brain_signal_{digest}"
