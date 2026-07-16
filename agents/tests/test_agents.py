import pytest

from cauco_agents import AgentRegistry, OperationsAgent, OperationsInput


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
