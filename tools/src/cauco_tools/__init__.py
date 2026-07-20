from cauco_tools.base import BaseTool
from cauco_tools.adapter_registry import ToolAdapterRegistry
from cauco_tools.execution import (
    ToolExecutionError,
    ToolExecutionRequest,
    ToolExecutionResult,
    ToolExecutionTimeoutError,
)
from cauco_tools.git_mutation import GitAddInput, GitCommitInput, GitPushInput
from cauco_tools.builtin import BUILTIN_TOOLS
from cauco_tools.models import (
    ToolCategory,
    ToolDefinition,
    ToolOperation,
    ToolPermission,
    ToolValidationResult,
)
from cauco_tools.registry import ToolRegistry


def create_default_registry() -> ToolRegistry:
    registry = ToolRegistry()
    for tool in BUILTIN_TOOLS:
        registry.register(tool)
    return registry


__all__ = [
    "BUILTIN_TOOLS",
    "BaseTool",
    "ToolCategory",
    "ToolAdapterRegistry",
    "ToolDefinition",
    "ToolOperation",
    "ToolPermission",
    "ToolRegistry",
    "ToolValidationResult",
    "ToolExecutionError",
    "ToolExecutionRequest",
    "ToolExecutionResult",
    "ToolExecutionTimeoutError",
    "GitAddInput",
    "GitCommitInput",
    "GitPushInput",
    "create_default_registry",
]
