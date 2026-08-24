from cauco_reasoning import (
    NoOpReasoningEngine,
    ReasoningEngine,
    ReasoningRequest,
    ReasoningService,
)


def test_noop_engine_satisfies_reasoning_protocol() -> None:
    engine = NoOpReasoningEngine()

    assert isinstance(engine, ReasoningEngine)


def test_noop_engine_does_not_claim_reasoning() -> None:
    service = ReasoningService(NoOpReasoningEngine())

    result = service.reason(
        ReasoningRequest(
            instruction="Muéstrame los últimos cinco correos",
            agent_id="email",
        )
    )

    assert result.provider == "noop"
    assert result.model is None
    assert result.text == ""
    assert result.reasoning_performed is False
    assert result.structured_data["reason"] == "reasoning_disabled"
    assert result.structured_data["agent_id"] == "email"
