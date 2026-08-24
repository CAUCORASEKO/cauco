from cauco_reasoning import (
    NoOpReasoningEngine,
    ReasoningRequirementResolver,
    ReasoningService,
)

from cauco_core.config import Settings
from cauco_core.main import create_app
from cauco_core.reasoning import (
    ReasoningAwarePlanningService,
    ReasoningOrchestrationService,
    ReasoningPlanningBridge,
    ReasoningProposalValidator,
)


def test_core_bootstraps_reasoning_boundary() -> None:
    app = create_app()

    assert isinstance(
        app.state.reasoning_requirement_resolver,
        ReasoningRequirementResolver,
    )
    assert isinstance(app.state.reasoning_service, ReasoningService)
    assert isinstance(
        app.state.reasoning_orchestration_service,
        ReasoningOrchestrationService,
    )
    assert isinstance(app.state.reasoning_proposal_validator, ReasoningProposalValidator)
    assert app.state.reasoning_proposal_validator.agent_registry is app.state.agent_registry
    assert isinstance(app.state.reasoning_planning_bridge, ReasoningPlanningBridge)
    assert isinstance(
        app.state.reasoning_aware_planning_service,
        ReasoningAwarePlanningService,
    )
    assert isinstance(
        app.state.reasoning_service.engine,
        NoOpReasoningEngine,
    )


def test_explicit_deepagents_configuration_is_bootstrapped_without_invocation() -> None:
    app = create_app(
        Settings(
            reasoning_enabled=True,
            reasoning_provider="deepagents",
            reasoning_model="openai:test-model",
        )
    )

    assert app.state.reasoning_service.engine.model == "openai:test-model"
