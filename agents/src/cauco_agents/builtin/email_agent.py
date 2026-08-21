import re

from cauco_agents.base import AgentMetadata
from cauco_agents.builtin.base import DeterministicSignalAgent
from cauco_agents.models import (
    AgentContext,
    AgentPlan,
    EmailDraftInput,
    EmailListMessagesInput,
)
from cauco_agents.skills import (
    EmailInspectInboxInput,
    EmailPrepareDraftInput,
    SkillRegistry,
    create_default_skill_registry,
)


class EmailAgent(DeterministicSignalAgent):
    metadata = AgentMetadata(
        agent_id="email",
        name="Email Agent",
        description="Recognizes bounded email inbox inspection and draft preparation requests.",
        version="1.0.0",
        capabilities=("email_inbox_inspection_proposal", "email_draft_proposal"),
        supported_intents=("email",),
        priority=25,
    )

    signals = (
        "email",
        "emails",
        "mail",
        "correo",
        "correos",
        "mensaje",
        "mensajes",
        "borrador",
        "borradores",
        "draft",
        "drafts",
    )

    def __init__(self, skill_registry: SkillRegistry | None = None) -> None:
        self.skill_registry = skill_registry or create_default_skill_registry()

    def summary(self) -> str:
        return (
            "This request belongs to Email planning, but no email was created or sent."
        )

    def proposed_actions(self) -> tuple[str, ...]:
        return (
            "Inspect bounded Apple Mail inbox metadata for explicit read requests.",
            "Resolve the exact recipient, subject, and body for draft requests.",
            "Prepare an Apple Mail draft only from complete typed details.",
            "Require preview and separate confirmation before creating the draft.",
        )

    def requires_confirmation(self) -> bool:
        return True

    def plan(
        self,
        context: AgentContext,
        *,
        allow_execution: bool = False,
    ) -> AgentPlan:
        inspection = is_inbox_inspection_request(context.instruction)

        if inspection:
            list_input, open_questions = resolve_email_inbox(context.instruction)
            compilation = self.skill_registry.get("email.inspect_inbox").compile(
                EmailInspectInboxInput(
                    list_input=list_input,
                    open_questions=open_questions,
                )
            )
        else:
            draft_input, open_questions = resolve_email_draft(context.instruction)
            compilation = self.skill_registry.get("email.prepare_draft").compile(
                EmailPrepareDraftInput(
                    draft_input=draft_input,
                    open_questions=open_questions,
                )
            )

        warnings = [
            "No email was created or sent during planning.",
            "Email sending is not supported by this workflow.",
        ]

        if inspection:
            warnings.append(
                "Inbox inspection is bounded to metadata and does not expose message bodies or attachments."
            )

        warnings.extend(compilation.warnings)

        if allow_execution:
            warnings.append(
                "allow_execution was ignored; execution requires review, approval, and runtime."
            )

        return AgentPlan(
            agent_id=self.id,
            agent_name=self.metadata.name,
            status="proposal_only",
            objective=f"Prepare a safe Email workflow for: {context.instruction}",
            context_used=bool(context.memory_references),
            steps=compilation.steps,
            open_questions=compilation.open_questions,
            warnings=tuple(warnings),
            requires_confirmation=not inspection,
            metadata={
                "framework_phase": "email_skill_v1",
                "skill_id": compilation.skill_id,
                "operation_input_complete": not compilation.open_questions,
            },
        )


def is_inbox_inspection_request(instruction: str) -> bool:
    normalized = instruction.casefold()

    draft_signal = re.search(
        r"\b(draft|drafts|borrador|borradores|prepare|prepara|preparar|"
        r"compose|redact|redacta|redactar|write|escribe|escribir)\b",
        normalized,
    )
    if draft_signal is not None:
        return False

    return bool(
        re.search(
            r"\b(inbox|bandeja|recibidos|received|"
            r"show|list|read|check|inspect|review|"
            r"muestra|muéstrame|mostrar|lista|listar|lee|leer|"
            r"revisa|revisar|últimos|ultimos|últimas|ultimas|"
            r"latest|recent)\b",
            normalized,
        )
    )


def resolve_email_inbox(
    instruction: str,
) -> tuple[EmailListMessagesInput | None, tuple[str, ...]]:
    normalized = instruction.casefold()

    match = re.search(
        r"\b(?:last|latest|recent|últimos|ultimos|últimas|ultimas)\s+(\d{1,3})\b",
        normalized,
    )

    if match is None:
        match = re.search(
            r"\b(\d{1,3})\s+(?:emails?|mails?|correos?|mensajes?)\b",
            normalized,
        )

    limit = 20 if match is None else int(match.group(1))

    if not 1 <= limit <= 20:
        return None, (
            "How many inbox messages should be inspected? The supported limit is between 1 and 20.",
        )

    return EmailListMessagesInput(limit=limit), ()


def resolve_email_draft(
    instruction: str,
) -> tuple[EmailDraftInput | None, tuple[str, ...]]:
    questions: list[str] = []

    recipient = _recipient(instruction)
    subject = _subject(instruction)
    body = _body(instruction)

    if recipient is None:
        questions.append("Which exact email address should receive the draft?")

    if subject is None:
        questions.append("What exact subject should the draft have?")

    if body is None:
        questions.append("What exact body should the draft contain?")

    if questions:
        return None, tuple(questions)

    try:
        return EmailDraftInput(recipient, subject, body), ()
    except ValueError:
        return None, ("The requested email draft details are invalid.",)


def _recipient(instruction: str) -> str | None:
    match = re.search(
        r"\b[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@"
        r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?"
        r"(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)+\b",
        instruction,
    )
    return match.group(0) if match is not None else None


def _subject(instruction: str) -> str | None:
    match = re.search(
        r"(?:asunto|subject)\s*[:=]\s*[\"“]?"
        r"(.+?)"
        r"(?=\s+(?:cuerpo|body|mensaje)\s*[:=]|[\"”]?\s*$)",
        instruction,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if match is None:
        return None

    value = " ".join(match.group(1).strip().rstrip('"”').split())
    return value or None


def _body(instruction: str) -> str | None:
    match = re.search(
        r"(?:cuerpo|body|mensaje)\s*[:=]\s*[\"“]?(.+?)[\"”]?$",
        instruction,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if match is None:
        return None

    value = match.group(1).strip()
    return value or None
