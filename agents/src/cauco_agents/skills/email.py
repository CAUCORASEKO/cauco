from dataclasses import dataclass

from cauco_agents.models import AgentPlanStep, AgentToolReference, EmailDraftInput
from cauco_agents.skills.models import SkillCompilation, SkillDefinition


@dataclass(frozen=True, slots=True)
class EmailPrepareDraftInput:
    draft_input: EmailDraftInput | None
    open_questions: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "open_questions", tuple(self.open_questions))


class EmailPrepareDraftSkill:
    definition = SkillDefinition(
        skill_id="email.prepare_draft",
        version=1,
        description="Compile a preview-first Apple Mail draft creation step.",
        supported_agent_ids=("email",),
    )

    def compile(self, input_data: EmailPrepareDraftInput) -> SkillCompilation:
        steps: tuple[AgentPlanStep, ...] = ()

        if input_data.draft_input is not None:
            steps = (
                AgentPlanStep(
                    1,
                    "Prepare email draft creation",
                    "Create only the exact approved draft after preview and confirmation.",
                    (),
                    "Create the approved Apple Mail draft through the mutation boundary.",
                    True,
                    False,
                    (
                        "Draft creation requires a separate single-use confirmation.",
                        "The draft must not be sent automatically.",
                    ),
                    AgentToolReference("email", "draft"),
                    input_data.draft_input,
                ),
            )

        return SkillCompilation(
            self.definition.skill_id,
            self.definition.version,
            steps,
            open_questions=input_data.open_questions,
        )
