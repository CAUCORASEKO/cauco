from threading import RLock

from cauco_tools.adapters.base import ToolRuntimeAdapter


class ToolAdapterRegistry:
    def __init__(self) -> None:
        self._adapters: dict[tuple[str, str], ToolRuntimeAdapter] = {}
        self._lock = RLock()

    def register(self, adapter: ToolRuntimeAdapter) -> None:
        with self._lock:
            for operation in adapter.operations:
                key = (adapter.tool_id, operation)
                if key in self._adapters:
                    raise ValueError(
                        f"Runtime adapter for '{adapter.tool_id}.{operation}' already exists."
                    )
                self._adapters[key] = adapter

    def get(self, tool_id: str, operation_id: str) -> ToolRuntimeAdapter:
        with self._lock:
            try:
                return self._adapters[(tool_id, operation_id)]
            except KeyError as error:
                raise KeyError(
                    f"No runtime adapter for '{tool_id}.{operation_id}'."
                ) from error

    def exists(self, tool_id: str, operation_id: str) -> bool:
        with self._lock:
            return (tool_id, operation_id) in self._adapters
