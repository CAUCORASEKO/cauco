from collections import Counter

from cauco_core.memory.models import (
    MemoryKind,
    MemoryLayer,
    MemoryObject,
    MemoryRegistrySummary,
)


class MemoryRegistry:
    def __init__(self, objects: list[MemoryObject] | None = None) -> None:
        self.replace(objects or [])

    def replace(self, objects: list[MemoryObject]) -> None:
        ordered = sorted(
            objects,
            key=lambda item: (item.relative_path.casefold(), item.relative_path),
        )
        self._objects = ordered
        self._by_id = {item.id: item for item in ordered}

    def list_all(self) -> list[MemoryObject]:
        return list(self._objects)

    def get(self, memory_id: str) -> MemoryObject | None:
        return self._by_id.get(memory_id)

    def get_by_kind(self, kind: MemoryKind) -> list[MemoryObject]:
        return [item for item in self._objects if item.kind is kind]

    def get_by_layer(self, layer: MemoryLayer) -> list[MemoryObject]:
        return [item for item in self._objects if item.layer is layer]

    def summary(self) -> MemoryRegistrySummary:
        kinds = Counter(item.kind for item in self._objects)
        layers = Counter(item.layer for item in self._objects)
        return MemoryRegistrySummary(
            total=len(self._objects),
            by_kind={kind: kinds[kind] for kind in MemoryKind},
            by_layer={layer: layers[layer] for layer in MemoryLayer},
        )
