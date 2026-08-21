from dataclasses import dataclass

from cauco_agents.models import (
    AgentPlanStep,
    AgentToolReference,
    EmailDraftInput,
    EmailListAccountsInput,
    EmailListMailboxesInput,
    EmailListMessagesInput,
)
from cauco_agents.skills.models import SkillCompilation, SkillDefinition


@dataclass(frozen=True, slots=True)
class EmailInspectInboxInput:
    operation_input: (
        EmailListAccountsInput | EmailListMailboxesInput | EmailListMessagesInput | None
    )
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

        if input_data.operation_input is not None:
            operation_id, title, description, proposed_action = _inspection_step(
                input_data.operation_input
            )
            steps = (
                AgentPlanStep(
                    1,
                    title,
                    description,
                    (),
                    proposed_action,
                    False,
                    False,
                    (
                        "Email inspection is metadata-only.",
                        "Message bodies and attachments are not exposed.",
                    ),
                    AgentToolReference("email", operation_id),
                    input_data.operation_input,
                ),
            )

        return SkillCompilation(
            self.definition.skill_id,
            self.definition.version,
            steps,
            open_questions=input_data.open_questions,
        )


def _inspection_step(operation_input):
    if isinstance(operation_input, EmailListAccountsInput):
        return (
            "list_accounts",
            "Discover available email accounts",
            "List bounded visible Apple Mail account metadata without selecting an account.",
            "Discover accounts through the native email boundary for explicit selection.",
        )
    if isinstance(operation_input, EmailListMailboxesInput):
        return (
            "list_mailboxes",
            "Discover mailboxes for the selected account",
            "List bounded mailbox names for the exact explicit account reference.",
            "Discover mailboxes for explicit selection without assuming Inbox.",
        )
    return (
        "list_messages",
        "Inspect recent messages in the selected mailbox",
        "Read bounded metadata from the exact explicit mailbox reference.",
        "List recent message metadata through the native email boundary.",
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
