from cauco_reasoning import (
    DeepAgentsReasoningEngine,
    NoOpReasoningEngine,
    ReasoningEngine,
)

from cauco_core.config import Settings


def build_reasoning_engine(settings: Settings) -> ReasoningEngine:
    """Build the explicitly configured advisory reasoning engine."""
    if not settings.reasoning_enabled or settings.reasoning_provider == "noop":
        return NoOpReasoningEngine()
    if settings.reasoning_provider == "deepagents":
        if settings.reasoning_model is None:
            raise ValueError("Deep Agents reasoning requires an explicit model.")
        return DeepAgentsReasoningEngine(settings.reasoning_model)
    raise ValueError("Unsupported reasoning provider.")
