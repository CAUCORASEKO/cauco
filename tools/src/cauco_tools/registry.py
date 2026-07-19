from threading import RLock

from cauco_tools.models import (
    ToolCategory,
    ToolDefinition,
    ToolOperation,
    ToolValidationResult,
)


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, ToolDefinition] = {}
        self._lock = RLock()

    def register(self, tool: ToolDefinition) -> None:
        with self._lock:
            if tool.id in self._tools:
                raise ValueError(f"Tool '{tool.id}' is already registered.")
            self._tools[tool.id] = tool

    def get(self, tool_id: str) -> ToolDefinition:
        with self._lock:
            try:
                return self._tools[tool_id]
            except KeyError as error:
                raise KeyError(f"Unknown tool '{tool_id}'.") from error

    def list(self) -> tuple[ToolDefinition, ...]:
        with self._lock:
            return tuple(self._tools[key] for key in sorted(self._tools))

    def list_metadata(self) -> tuple[ToolDefinition, ...]:
        return self.list()

    def exists(self, tool_id: str) -> bool:
        with self._lock:
            return tool_id in self._tools

    def categories(self) -> tuple[ToolCategory, ...]:
        with self._lock:
            return tuple(
                sorted({tool.category for tool in self._tools.values()}, key=str)
            )

    def operations(self, tool_id: str) -> tuple[ToolOperation, ...]:
        tool = self.get(tool_id)
        return tuple(sorted(tool.operations, key=lambda operation: operation.id))

    def validate(self, tool_id: str, operation_id: str) -> ToolValidationResult:
        with self._lock:
            tool = self._tools.get(tool_id)
            if tool is None:
                return ToolValidationResult(
                    tool_id=tool_id,
                    operation_id=operation_id,
                    valid=False,
                    tool_exists=False,
                    operation_exists=False,
                    tool_enabled=False,
                    operation_enabled=False,
                    safe=None,
                    confirmation_required=None,
                    execution_enabled=False,
                    reason="Tool is not registered.",
                )
            operation = next(
                (item for item in tool.operations if item.id == operation_id), None
            )
            if operation is None:
                return ToolValidationResult(
                    tool_id=tool_id,
                    operation_id=operation_id,
                    valid=False,
                    tool_exists=True,
                    operation_exists=False,
                    tool_enabled=tool.enabled,
                    operation_enabled=False,
                    safe=None,
                    confirmation_required=None,
                    execution_enabled=False,
                    reason="Operation is not registered for this tool.",
                )
            valid = tool.enabled and operation.enabled
            reason = None if valid else "Tool or operation is disabled."
            return ToolValidationResult(
                tool_id=tool_id,
                operation_id=operation_id,
                valid=valid,
                tool_exists=True,
                operation_exists=True,
                tool_enabled=tool.enabled,
                operation_enabled=operation.enabled,
                safe=operation.safe,
                confirmation_required=operation.confirmation_required,
                execution_enabled=False,
                runtime_execution_allowed=operation.runtime_execution_allowed,
                mutation=operation.mutation,
                preview_required=operation.preview_required,
                reason=reason,
            )

    def __len__(self) -> int:
        with self._lock:
            return len(self._tools)
