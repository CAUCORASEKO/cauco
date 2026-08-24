from cauco_reasoning.base import ReasoningEngine
from cauco_reasoning.models import ReasoningRequest, ReasoningResult


class ReasoningService:
    """Coordinates access to the configured reasoning engine."""

    def __init__(self, engine: ReasoningEngine) -> None:
        self.engine = engine

    def reason(self, request: ReasoningRequest) -> ReasoningResult:
        return self.engine.reason(request)
