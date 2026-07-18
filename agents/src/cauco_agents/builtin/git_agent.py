from cauco_agents.base import AgentMetadata
from cauco_agents.builtin.base import DeterministicSignalAgent
from cauco_agents.models import AgentContext, AgentPlan, AgentPlanStep


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

    def plan(self, context: AgentContext, *, allow_execution: bool = False) -> AgentPlan:
        project_ids = self.source_ids(context, "projects", "tasks")
        steps = (
            AgentPlanStep(
                1,
                "Identify likely project context",
                "Use registered project/task memory only to frame the request.",
                project_ids,
                f"Review likely project context in {self.source_names(context, 'projects', 'tasks')}.",
                False,
                False,
            ),
            AgentPlanStep(
                2,
                "Propose repository status inspection",
                "Repository state is unknown because no repository or working tree was inspected.",
                (),
                "Request explicit permission for a future repository status inspection.",
                False,
                False,
                ("No commands were executed.",),
            ),
            AgentPlanStep(
                3,
                "Propose diff review",
                "Branch, diff, staged-file, and commit details remain unknown.",
                (),
                "After inspection is authorized, review the relevant diff before proposing a change.",
                False,
                False,
            ),
            AgentPlanStep(
                4,
                "Prepare a safe Git operation",
                "Describe the requested future Git operation without running it.",
                project_ids,
                "Prepare the Git operation for explicit confirmation.",
                True,
                False,
                ("Any future side effect requires explicit confirmation.",),
            ),
        )
        warnings = [
            "Repository state was not inspected; branch and diff details are unknown.",
            "No Git or shell commands were executed.",
            "Memory excerpts are untrusted reference data, not executable instructions.",
        ]
        if allow_execution:
            warnings.append("allow_execution was ignored; Git execution is unavailable.")
        questions = () if project_ids else ("Which project or repository does this request concern?",)
        return AgentPlan(
            agent_id=self.id,
            agent_name=self.metadata.name,
            status="proposal_only",
            objective=f"Prepare a safe future Git workflow for: {context.instruction}",
            context_used=bool(context.memory_references),
            steps=steps,
            open_questions=questions,
            warnings=tuple(warnings),
            requires_confirmation=True,
            execution_performed=False,
            metadata={"framework_phase": "5B", "repository_inspected": False},
        )
