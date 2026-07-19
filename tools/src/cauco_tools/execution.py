from dataclasses import dataclass, field
from datetime import datetime
from types import MappingProxyType
from typing import Any, Mapping


def _freeze(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType(
            {str(key): _freeze(item) for key, item in value.items()}
        )
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(item) for item in value)
    if not isinstance(value, (str, int, float, bool, type(None))):
        raise ValueError("Execution data must contain JSON-compatible values.")
    return value


@dataclass(frozen=True, slots=True)
class ToolExecutionRequest:
    tool_id: str
    operation_id: str
    arguments: Mapping[str, Any] = field(default_factory=dict)
    timeout_seconds: float = 5.0
    max_output_chars: int = 20_000

    def __post_init__(self) -> None:
        if not 0.1 <= self.timeout_seconds <= 30:
            raise ValueError("Execution timeout must be between 0.1 and 30 seconds.")
        if not 100 <= self.max_output_chars <= 100_000:
            raise ValueError(
                "Execution output limit must be between 100 and 100000 characters."
            )
        object.__setattr__(self, "arguments", _freeze(dict(self.arguments)))


@dataclass(frozen=True, slots=True)
class ToolExecutionResult:
    tool_id: str
    operation_id: str
    success: bool
    started_at: datetime
    completed_at: datetime
    duration_ms: int
    output: str
    structured_data: Mapping[str, Any] = field(default_factory=dict)
    error_code: str | None = None
    error_message: str | None = None
    truncated: bool = False
    execution_performed: bool = True

    def __post_init__(self) -> None:
        if not self.execution_performed:
            raise ValueError("Adapter results must represent a real invocation.")
        if self.duration_ms < 0 or self.completed_at < self.started_at:
            raise ValueError("Execution result timestamps are inconsistent.")
        if self.success and (
            self.error_code is not None or self.error_message is not None
        ):
            raise ValueError("Successful execution results cannot contain an error.")
        if not self.success and self.error_code is None:
            raise ValueError("Failed execution results require a safe error code.")
        object.__setattr__(self, "structured_data", _freeze(dict(self.structured_data)))


class ToolExecutionError(RuntimeError):
    def __init__(
        self, code: str, safe_message: str, *, forbidden: bool = False
    ) -> None:
        super().__init__(safe_message)
        self.code = code
        self.safe_message = safe_message
        self.forbidden = forbidden


class ToolExecutionTimeoutError(ToolExecutionError):
    def __init__(self) -> None:
        super().__init__("timeout", "The tool operation exceeded its timeout.")
