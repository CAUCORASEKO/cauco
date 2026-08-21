from dataclasses import dataclass

from cauco_agents.models import (
    AgentPlanStep,
    AgentToolReference,
    EmailDraftInput,
    EmailListMessagesInput,
)
from cauco_agents.skills.models import SkillCompilation, SkillDefinition


@dataclass(frozen=True, slots=True)
class EmailInspectInboxInput:
    list_input: EmailListMessagesInput | None
    open_questions: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "open_questions", tuple(self.open_questions))


class EmailInspectInboxSkill:
    definition = SkillDefinition(
        skill_id="email.inspect_inbox",
        version=1,
        description="Compile a bounded read-only Apple Mail inbox inspection step.",
        supported_agent_ids=("email",),
    )

    def compile(self, input_data: EmailInspectInboxInput) -> SkillCompilation:
        steps: tuple[AgentPlanStep, ...] = ()

        if input_data.list_input is not None:
            steps = (
                AgentPlanStep(
                    1,
                    "Inspect recent inbox messages",
                    "Read bounded Apple Mail inbox metadata without message bodies or attachments.",
                    (),
                    "List recent inbox message metadata through the native email boundary.",
                    False,
                    False,
                    (
                        "Inbox inspection is metadata-only.",
                        "Message bodies and attachments are not exposed.",
                    ),
                    AgentToolReference("email", "list_messages"),
                    input_data.list_input,
                ),
            )

        return SkillCompilation(
            self.definition.skill_id,
            self.definition.version,
            steps,
            open_questions=input_data.open_questions,
        )


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
