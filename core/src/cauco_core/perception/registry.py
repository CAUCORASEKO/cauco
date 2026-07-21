from cauco_core.perception.models import PerceptionSourceMetadata
from cauco_core.perception.source import PerceptionSource


class PerceptionSourceRegistry:
    def __init__(self) -> None:
        self._sources: dict[str, PerceptionSource] = {}

    def register(self, source: PerceptionSource) -> None:
        source_id = source.metadata.source_id
        if source_id in self._sources:
            raise ValueError(f"Perception source '{source_id}' is already registered.")
        self._sources[source_id] = source

    def get(self, source_id: str) -> PerceptionSource:
        try:
            return self._sources[source_id]
        except KeyError as error:
            raise KeyError(f"Unknown perception source '{source_id}'.") from error

    def list_sources(self) -> tuple[PerceptionSource, ...]:
        return tuple(self._sources[source_id] for source_id in sorted(self._sources))

    def list_metadata(self) -> tuple[PerceptionSourceMetadata, ...]:
        return tuple(source.metadata for source in self.list_sources())

    def __len__(self) -> int:
        return len(self._sources)
