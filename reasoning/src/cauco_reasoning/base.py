from typing import Protocol, runtime_checkable

from cauco_reasoning.models import ReasoningRequest, ReasoningResult


@runtime_checkable
class ReasoningEngine(Protocol):
    """Provider-neutral reasoning boundary used by Cauco."""

    def reason(self, request: ReasoningRequest) -> ReasoningResult:
        """Reason over a bounded request without bypassing Cauco execution policy."""
        ...
