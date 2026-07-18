from cauco_agents.base import AgentMetadata
from cauco_agents.builtin.base import DeterministicSignalAgent


class ResearchAgent(DeterministicSignalAgent):
    metadata = AgentMetadata(
        agent_id="research",
        name="Research Agent",
        description="Recognizes research, comparison, and source-discovery requests.",
        version="1.0.0",
        capabilities=("research_planning", "comparison_planning", "source_planning"),
        supported_intents=("research",),
        priority=30,
    )
    signals = (
        "research",
        "investigate",
        "compare",
        "analyze",
        "find information",
        "look up",
        "sources",
        "documentation",
        "paper",
        "repo analysis",
    )

    def summary(self) -> str:
        return "This request belongs to research planning."

    def proposed_actions(self) -> tuple[str, ...]:
        return (
            "Define the research question and comparison criteria.",
            "Identify the source types that would be needed.",
            "Gather and analyze sources only after external retrieval is explicitly enabled.",
        )

    def base_warnings(self) -> tuple[str, ...]:
        return (
            "External retrieval is not enabled in Phase 5A; no web or external files were accessed.",
        )

    def requires_confirmation(self) -> bool:
        return False
