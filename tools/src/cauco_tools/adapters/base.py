from typing import Protocol

from cauco_tools.execution import ToolExecutionRequest, ToolExecutionResult


class ToolRuntimeAdapter(Protocol):
    tool_id: str
    operations: frozenset[str]

    def execute(self, request: ToolExecutionRequest) -> ToolExecutionResult:
        """Execute one fixed, typed, allowlisted operation."""
