from cauco_agents.base import AgentMetadata
from cauco_agents.builtin.base import DeterministicSignalAgent


class ProjectAgent(DeterministicSignalAgent):
    metadata = AgentMetadata(
        agent_id="project",
        name="Project Agent",
        description="Recognizes project planning and work-management requests.",
        version="1.0.0",
        capabilities=("project_planning", "task_proposals", "priority_review"),
        supported_intents=("planning", "project"),
        priority=10,
    )
    signals = (
        "project",
        "milestone",
        "roadmap",
        "sprint",
        "priority",
        "task",
        "blocker",
        "next step",
        "work on",
        "plan",
        "phase",
    )

    def summary(self) -> str:
        return "This request belongs to deterministic project planning."

    def proposed_actions(self) -> tuple[str, ...]:
        return (
            "Review the relevant project and task memory.",
            "Identify priorities, blockers, milestones, or next steps.",
            "Prepare any task update through the controlled memory-write proposal workflow.",
        )

    def requires_confirmation(self) -> bool:
        return True
