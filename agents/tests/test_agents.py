import subprocess
import urllib.request
from dataclasses import FrozenInstanceError

import pytest

from cauco_agents import (
    AgentMatch,
    AgentMetadata,
    AgentRegistry,
    AgentRequest,
    AgentResult,
    AgentRouter,
    BaseAgent,
    CalendarAgent,
    GitAgent,
    OperationsAgent,
    OperationsInput,
    ProjectAgent,
    ResearchAgent,
    UnknownPreferredAgentError,
    create_default_registry,
)


def test_operations_agent_summary() -> None:
    summary = OperationsAgent().run(
        OperationsInput(
            runtime_state="online",
            memory_file_count=5,
            registered_agents=1,
            registered_tools=3,
            scheduler_job_count=0,
        )
    )
    assert summary == (
        "Runtime: online\nMemory files: 5\nRegistered agents: 1\n"
        "Registered tools: 3\nScheduler jobs: 0"
    )


def test_registry_rejects_duplicate_agent() -> None:
    registry = AgentRegistry()
    agent = OperationsAgent()
    registry.register(agent)
    with pytest.raises(ValueError, match="already registered"):
        registry.register(agent)


def test_operations_input_rejects_negative_counts() -> None:
    with pytest.raises(ValueError, match="cannot be negative"):
        OperationsInput("online", -1, 1, 3, 0)


def test_base_agent_metadata_contract() -> None:
    metadata = ProjectAgent().metadata
    assert metadata.agent_id == "project"
    assert metadata.version == "1.0.0"
    assert metadata.capabilities
    assert metadata.supported_intents == ("planning", "project")
    assert metadata.uses_model is False


def test_registry_order_lookup_and_immutable_metadata() -> None:
    registry = AgentRegistry()
    registry.register(ResearchAgent())
    registry.register(ProjectAgent())
    registry.register(GitAgent())
    registry.register(CalendarAgent())

    assert [item.agent_id for item in registry.list_metadata()] == [
        "calendar",
        "git",
        "project",
        "research",
    ]
    assert registry.get("project").metadata.name == "Project Agent"
    with pytest.raises(KeyError, match="Unknown agent"):
        registry.get("missing")
    with pytest.raises(FrozenInstanceError):
        registry.list_metadata()[0].name = "Changed"  # type: ignore[misc]


@pytest.mark.parametrize(
    ("agent", "instruction", "signal"),
    [
        (ProjectAgent(), "What should I work on next in Cauco?", "work on"),
        (GitAgent(), "Commit my latest changes.", "commit"),
        (ResearchAgent(), "Research MCP support for local assistants.", "research"),
        (CalendarAgent(), "Crea un evento mañana.", "evento"),
    ],
)
def test_builtin_positive_matches(
    agent: BaseAgent, instruction: str, signal: str
) -> None:
    match = agent.can_handle(AgentRequest(instruction))
    assert match.matched is True
    assert match.score >= 40
    assert signal in match.matched_signals


def test_unrelated_request_has_no_match() -> None:
    routed = AgentRouter(create_default_registry()).route(
        AgentRequest("Tell me a joke.")
    )
    assert routed.selected_agent_id is None
    assert routed.result is None
    assert all(match.score == 0 for match in routed.matches)


def test_scoring_is_stable() -> None:
    request = AgentRequest("Review the git diff and prepare a commit.")
    agent = GitAgent()
    assert agent.can_handle(request) == agent.can_handle(request)
    assert agent.can_handle(request).score == 70


class StubAgent(BaseAgent):
    def __init__(self, agent_id: str, priority: int) -> None:
        self.metadata = AgentMetadata(
            agent_id=agent_id,
            name=f"{agent_id} agent",
            description="Tie-breaking test agent.",
            priority=priority,
        )

    def can_handle(self, request: AgentRequest) -> AgentMatch:
        return AgentMatch(
            self.id, True, 50, ("same",), ("Same score.",), self.metadata.priority
        )

    def execute(self, request: AgentRequest) -> AgentResult:
        return AgentResult(
            self.id,
            self.metadata.name,
            "proposal_only",
            "Test proposal.",
            (),
            (),
            False,
        )


def test_router_tie_breaks_by_priority_then_agent_id() -> None:
    registry = AgentRegistry()
    registry.register(StubAgent("zeta", 20))
    registry.register(StubAgent("beta", 30))
    registry.register(StubAgent("alpha", 30))
    routed = AgentRouter(registry).route(AgentRequest("same"))
    assert routed.selected_agent_id == "alpha"


def test_preferred_agent_is_accepted_only_when_relevant() -> None:
    router = AgentRouter(create_default_registry())
    accepted = router.route(AgentRequest("Review this diff", preferred_agent_id="git"))
    rejected = router.route(
        AgentRequest("Research MCP support", preferred_agent_id="git")
    )

    assert accepted.selected_agent_id == "git"
    assert accepted.preferred_agent_rejected is False
    assert rejected.selected_agent_id == "research"
    assert rejected.preferred_agent_rejected is True
    assert rejected.result is not None
    assert "preferred agent" in rejected.result.warnings[-1]


def test_unknown_preferred_agent_is_rejected() -> None:
    with pytest.raises(UnknownPreferredAgentError, match="Unknown preferred agent"):
        AgentRouter(create_default_registry()).route(
            AgentRequest("Plan the project", preferred_agent_id="missing")
        )


def test_request_rejects_empty_and_normalizes_whitespace() -> None:
    with pytest.raises(ValueError, match="cannot be empty"):
        AgentRequest("  \n  ")
    assert AgentRequest("  Plan   the\nproject  ").instruction == "Plan the project"


@pytest.mark.parametrize(
    "agent", [ProjectAgent(), GitAgent(), ResearchAgent(), CalendarAgent()]
)
def test_builtin_results_are_safe(agent: BaseAgent) -> None:
    result = agent.execute(AgentRequest("Relevant request", allow_execution=True))
    assert result.status == "proposal_only"
    assert result.execution_performed is False
    assert result.proposed_actions
    assert any("ignored" in warning for warning in result.warnings)


def test_agents_do_not_invoke_subprocess_or_network(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def unexpected_call(*args: object, **kwargs: object) -> None:
        raise AssertionError("External execution was attempted.")

    monkeypatch.setattr(subprocess, "run", unexpected_call)
    monkeypatch.setattr(urllib.request, "urlopen", unexpected_call)
    router = AgentRouter(create_default_registry())
    for instruction in ("Commit changes", "Plan the project", "Research Python"):
        result = router.route(AgentRequest(instruction, allow_execution=True)).result
        assert result is not None
        assert result.execution_performed is False


def test_request_context_is_bounded_and_defensively_copied() -> None:
    source = {"project": "Cauco"}
    request = AgentRequest("Plan work", context=source)
    source["project"] = "Changed"
    assert request.context["project"] == "Cauco"
    with pytest.raises(ValueError, match="more than 20"):
        AgentRequest("Plan work", context={str(index): index for index in range(21)})
