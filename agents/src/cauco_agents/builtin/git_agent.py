from cauco_agents.base import AgentMetadata
from cauco_agents.builtin.base import DeterministicSignalAgent


class GitAgent(DeterministicSignalAgent):
    metadata = AgentMetadata(
        agent_id="git",
        name="Git Agent",
        description="Recognizes repository and version-control operation requests.",
        version="1.0.0",
        capabilities=("repository_inspection_proposal", "change_review_proposal"),
        supported_intents=("git",),
        priority=20,
    )
    signals = (
        "git",
        "commit",
        "branch",
        "diff",
        "push",
        "pull",
        "merge",
        "repository",
        "repo",
        "working tree",
        "pull request",
        "tag",
        "release",
    )

    def summary(self) -> str:
        return "This request belongs to Git operations, but no repository was inspected."

    def proposed_actions(self) -> tuple[str, ...]:
        return (
            "Inspect repository status after explicit execution support is enabled.",
            "Review the relevant diff or branch state.",
            "Prepare the requested Git operation for explicit approval.",
        )

    def requires_confirmation(self) -> bool:
        return True
