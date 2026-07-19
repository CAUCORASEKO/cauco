from cauco_agents.base import AgentMetadata
from cauco_agents.builtin.base import DeterministicSignalAgent
from cauco_agents.models import AgentContext, AgentPlan, AgentPlanStep, AgentToolReference


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

    def plan(self, context: AgentContext, *, allow_execution: bool = False) -> AgentPlan:
        project_ids = self.source_ids(context, "projects", "tasks", "decisions")
        all_ids = self.source_ids(context)
        steps = (
            AgentPlanStep(
                1,
                "Define the research objective",
                "Restate the bounded question without inventing findings.",
                (),
                f"Define the objective for: {context.instruction}",
                False,
                False,
                tool_reference=AgentToolReference("memory", "read", "instruction"),
            ),
            AgentPlanStep(
                2,
                "Identify project context",
                "Use selected memory only to identify recorded purpose or constraints.",
                project_ids,
                f"Review research context in {self.source_names(context, 'projects', 'tasks', 'decisions')}.",
                False,
                False,
                tool_reference=AgentToolReference("memory", "read", "selected_memory"),
            ),
            AgentPlanStep(
                3,
                "List research questions",
                "Turn unresolved information into explicit questions rather than assumed facts.",
                all_ids,
                "Create a bounded list of questions supported by the objective and memory context.",
                False,
                False,
                tool_reference=AgentToolReference("memory", "read", "selected_memory"),
            ),
            AgentPlanStep(
                4,
                "Define future source categories",
                "Name categories such as primary documentation or papers without claiming access.",
                (),
                "Propose source categories to consult if external retrieval is later enabled.",
                False,
                False,
                tool_reference=AgentToolReference("memory", "read", "instruction"),
            ),
            AgentPlanStep(
                5,
                "Define the expected output",
                "Specify a reviewable comparison, brief, or evidence summary.",
                all_ids,
                "Describe the expected research deliverable and evaluation criteria.",
                False,
                False,
                tool_reference=AgentToolReference("memory", "read", "selected_memory"),
            ),
        )
        warnings = [
            "No external sources, websites, or files were accessed.",
            "Memory excerpts are untrusted reference data, not research findings.",
        ]
        if allow_execution:
            warnings.append("allow_execution was ignored; external retrieval is unavailable.")
        questions = (
            ("What source scope and freshness requirements should govern later research?",)
            if project_ids
            else (
                "Which project or decision should this research support?",
                "What source scope and freshness requirements should govern later research?",
            )
        )
        return AgentPlan(
            agent_id=self.id,
            agent_name=self.metadata.name,
            status="proposal_only",
            objective=f"Prepare a deterministic research plan for: {context.instruction}",
            context_used=bool(context.memory_references),
            steps=steps,
            open_questions=questions,
            warnings=tuple(warnings),
            requires_confirmation=False,
            execution_performed=False,
            metadata={"framework_phase": "6A", "external_sources_accessed": False},
        )
