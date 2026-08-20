from typing import Any, Protocol

from cauco_tools.execution import ToolExecutionRequest, ToolExecutionResult


class ToolRuntimeAdapter(Protocol):
    tool_id: str
    operations: frozenset[str]

    def execute(self, request: ToolExecutionRequest) -> ToolExecutionResult:
        """Execute one fixed, typed, allowlisted operation."""

    def preflight(self, request: ToolExecutionRequest) -> Any:
        """Optionally validate/inspect without mutating runtime state.

        This method is intentionally optional at runtime for compatibility
        with existing adapters. It may raise ToolExecutionError.
        """
