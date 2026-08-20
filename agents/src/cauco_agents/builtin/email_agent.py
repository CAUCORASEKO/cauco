import re

from cauco_agents.base import AgentMetadata
from cauco_agents.builtin.base import DeterministicSignalAgent
from cauco_agents.models import AgentContext, AgentPlan, EmailDraftInput
from cauco_agents.skills import (
    EmailPrepareDraftInput,
    SkillRegistry,
    create_default_skill_registry,
)


class EmailAgent(DeterministicSignalAgent):
    metadata = AgentMetadata(
        agent_id="email",
        name="Email Agent",
        description="Recognizes bounded email draft preparation requests.",
        version="1.0.0",
        capabilities=("email_draft_proposal",),
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
            "Resolve the exact recipient, subject, and body.",
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
            requires_confirmation=True,
            metadata={
                "framework_phase": "email_skill_v1",
                "skill_id": compilation.skill_id,
                "draft_input_complete": not compilation.open_questions,
            },
        )


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
