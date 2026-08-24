from cauco_reasoning import (
    NoOpReasoningEngine,
    ReasoningRequirementResolver,
    ReasoningService,
)

from cauco_core.main import create_app


def test_core_bootstraps_reasoning_boundary() -> None:
    app = create_app()

    assert isinstance(
        app.state.reasoning_requirement_resolver,
        ReasoningRequirementResolver,
    )
    assert isinstance(app.state.reasoning_service, ReasoningService)
    assert isinstance(
        app.state.reasoning_service.engine,
        NoOpReasoningEngine,
    )
