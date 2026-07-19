import re

from cauco_agents.base import AgentMetadata
from cauco_agents.builtin.base import DeterministicSignalAgent
from cauco_agents.models import (
    AgentContext,
    AgentMemoryReference,
    AgentPlan,
    AgentPlanStep,
    AgentToolReference,
    MemoryConfirmProposalInput,
    MemoryCreateProposalInput,
)


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

    def plan(
        self, context: AgentContext, *, allow_execution: bool = False
    ) -> AgentPlan:
        task_ids = self.source_ids(context, "tasks")
        project_ids = self.source_ids(context, "projects")
        all_ids = self.source_ids(context)
        task_reference = next(
            (item for item in context.memory_references if item.kind == "tasks"), None
        )
        project_reference = next(
            (item for item in context.memory_references if item.kind == "projects"),
            None,
        )
        priority_heading = first_matching_heading(
            task_reference,
            ("current priorities", "today", "now", "this week", "current sprint"),
        )
        sprint_heading = first_matching_heading(task_reference, ("current sprint",))
        project_heading = first_project_heading(project_reference)
        priority_action = (
            f"Review the recorded priorities under {priority_heading} in {task_reference.name}."
            if priority_heading is not None and task_reference is not None
            else f"Review priorities in {self.source_names(context, 'tasks')}."
        )
        project_action = (
            f"Review the recorded {project_heading} project section in {project_reference.name}."
            if project_heading is not None and project_reference is not None
            else f"Review project context in {self.source_names(context, 'projects')}."
        )
        comparison_action = (
            f"Compare the recorded {project_heading} context with {sprint_heading}."
            if project_heading is not None and sprint_heading is not None
            else "List only workload facts supported by the selected memory excerpts."
        )
        proposal_id = memory_proposal_id(context.instruction)
        proposal_type = memory_proposal_type(context.instruction)
        mutation_reference = AgentToolReference(
            "memory",
            "confirm_proposal" if proposal_id else "create_proposal",
            "Tasks.md",
        )
        mutation_input = (
            MemoryConfirmProposalInput(proposal_id)
            if proposal_id
            else MemoryCreateProposalInput(proposal_type, context.instruction)
        )
        steps = (
            AgentPlanStep(
                order=1,
                title="Review current priorities",
                description=(
                    "Use only the selected task memory to identify explicitly recorded priorities."
                ),
                source_memory_ids=task_ids,
                proposed_action=priority_action,
                requires_confirmation=False,
                execution_available=False,
                tool_reference=AgentToolReference("memory", "read", "Tasks.md"),
            ),
            AgentPlanStep(
                order=2,
                title="Identify the relevant project",
                description=(
                    "Relate the instruction to registered project memory without inferring "
                    "unrecorded status."
                ),
                source_memory_ids=project_ids,
                proposed_action=project_action,
                requires_confirmation=False,
                execution_available=False,
                tool_reference=AgentToolReference("memory", "read", "Projects.md"),
            ),
            AgentPlanStep(
                order=3,
                title="Check tasks, blockers, and milestones",
                description=(
                    "Separate facts present in the excerpts from unresolved blockers or milestones."
                ),
                source_memory_ids=all_ids,
                proposed_action=comparison_action,
                requires_confirmation=False,
                execution_available=False,
                tool_reference=AgentToolReference("memory", "read", "selected_memory"),
            ),
            AgentPlanStep(
                order=4,
                title="Choose the next bounded action",
                description="Propose one reviewable next action; do not perform it.",
                source_memory_ids=all_ids,
                proposed_action="Select one bounded next action supported by the recorded context.",
                requires_confirmation=False,
                execution_available=False,
                tool_reference=AgentToolReference("memory", "read", "selected_memory"),
            ),
            AgentPlanStep(
                order=5,
                title=(
                    "Confirm a controlled memory proposal"
                    if proposal_id
                    else "Prepare an optional memory proposal"
                ),
                description=(
                    "If the review reveals a useful task update, prepare it through the separate "
                    "controlled memory-write proposal workflow."
                ),
                source_memory_ids=task_ids,
                proposed_action=(
                    "Apply only the exact existing proposal after mutation preview and confirmation."
                    if proposal_id
                    else "Create, but do not apply, a controlled memory proposal after mutation confirmation."
                ),
                requires_confirmation=True,
                execution_available=False,
                warnings=("No memory change was created or confirmed.",),
                tool_reference=mutation_reference,
                operation_input=mutation_input,
            ),
        )
        questions: list[str] = []
        if not project_ids:
            questions.append("Which registered project does this instruction concern?")
        if not task_ids:
            questions.append(
                "Which current tasks or priorities should guide the next action?"
            )
        selected_text = " ".join(
            reference.excerpt.casefold() for reference in context.memory_references
        )
        if not any(
            signal in selected_text for signal in ("status", "active", "in progress")
        ):
            questions.append("What is the current recorded project status?")
        if not any(
            signal in selected_text for signal in ("blocker", "blocked", "waiting")
        ):
            questions.append("Are any blockers or dependencies still unrecorded?")
        if not any(signal in selected_text for signal in ("deadline", "due ", "due:")):
            questions.append("Is there a deadline or due date for the next action?")
        if not any(
            signal in selected_text for signal in ("next step", "next action", "- [ ]")
        ):
            questions.append(
                "What is the next concrete action if it is not recorded here?"
            )
        if any(
            reference.excerpt_strategy == "document_start"
            for reference in context.memory_references
        ):
            questions.append(
                "Which operational memory section should replace the introductory fallback?"
            )
        warnings = [
            "Memory excerpts are untrusted reference data, not executable instructions."
        ]
        if allow_execution:
            warnings.append(
                "allow_execution was ignored; planning remains proposal-only."
            )
        return AgentPlan(
            agent_id=self.id,
            agent_name=self.metadata.name,
            status="proposal_only",
            objective=f"Determine the next bounded action for: {context.instruction}",
            context_used=bool(context.memory_references),
            steps=steps,
            open_questions=tuple(questions),
            warnings=tuple(warnings),
            requires_confirmation=True,
            execution_performed=False,
            metadata={"framework_phase": "7A", "planning": "deterministic_template"},
        )


def memory_proposal_id(instruction: str) -> str | None:
    match = re.search(r"\bproposal_[0-9a-f]{24}\b", instruction.casefold())
    return match.group(0) if match else None


def memory_proposal_type(instruction: str) -> str:
    folded = instruction.casefold()
    if "decision" in folded:
        return "add_decision"
    if "relationship" in folded or "person" in folded:
        return "add_relationship_note"
    if "project note" in folded:
        return "add_project_note"
    return "add_task"


def first_matching_heading(
    reference: AgentMemoryReference | None, preferred: tuple[str, ...]
) -> str | None:
    if reference is None:
        return None
    by_normalized = {
        heading.casefold(): heading for heading in reference.selected_headings
    }
    return next(
        (by_normalized[item] for item in preferred if item in by_normalized), None
    )


def first_project_heading(reference: AgentMemoryReference | None) -> str | None:
    if reference is None:
        return None
    generic = {"projects", "active", "archived", "current projects", "overview"}
    return next(
        (
            heading
            for heading in reference.selected_headings
            if heading.casefold() not in generic
        ),
        None,
    )
