from dataclasses import FrozenInstanceError

import pytest

from cauco_agents import (
    AgentContext,
    EmailAgent,
    EmailDraftInput,
    EmailListMessagesInput,
)


def context(instruction: str) -> AgentContext:
    return AgentContext(
        agent_id="email",
        instruction=instruction,
        resolved_intent="email",
        memory_references=(),
        context_summary="",
        limitations=(),
        metadata={},
        learning_guidance=(),
    )


def test_email_draft_input_normalizes_and_is_immutable() -> None:
    value = EmailDraftInput(
        recipient=" claudio@aisosu.fi ",
        subject="  Prueba   Cauco ",
        body="Contenido.",
    )

    assert value.recipient == "claudio@aisosu.fi"
    assert value.subject == "Prueba Cauco"

    with pytest.raises(FrozenInstanceError):
        value.subject = "Changed"  # type: ignore[misc]


@pytest.mark.parametrize(
    "recipient",
    (
        "",
        "invalid",
        "@example.com",
        "user@",
        "user@example",
        "user @example.com",
    ),
)
def test_email_draft_input_rejects_invalid_recipient(recipient: str) -> None:
    with pytest.raises(ValueError):
        EmailDraftInput(recipient, "Subject", "Body")


def test_email_draft_input_enforces_real_body_boundary() -> None:
    EmailDraftInput("user@example.com", "Subject", "x" * 4000)

    with pytest.raises(ValueError, match="4000"):
        EmailDraftInput("user@example.com", "Subject", "x" * 4001)


def test_email_agent_builds_exact_draft_plan() -> None:
    plan = EmailAgent().plan(
        context(
            "Prepara un correo para claudio@aisosu.fi "
            "asunto: Prueba Cauco "
            "cuerpo: Este es un borrador creado por Cauco."
        )
    )

    assert plan.open_questions == ()
    assert len(plan.steps) == 1

    step = plan.steps[0]
    assert step.tool_reference.tool_id == "email"
    assert step.tool_reference.operation_id == "draft"
    assert step.requires_confirmation is True
    assert step.operation_input == EmailDraftInput(
        "claudio@aisosu.fi",
        "Prueba Cauco",
        "Este es un borrador creado por Cauco.",
    )


def test_email_agent_does_not_invent_missing_subject_or_body() -> None:
    plan = EmailAgent().plan(context("Prepara un correo para claudio@aisosu.fi"))

    assert plan.steps == ()
    assert "What exact subject should the draft have?" in plan.open_questions
    assert "What exact body should the draft contain?" in plan.open_questions


@pytest.mark.parametrize(
    ("instruction", "expected_limit"),
    (
        ("Muéstrame los últimos 5 correos", 5),
        ("Show my last 10 emails", 10),
        ("Revisa mi inbox", 20),
        ("Lista 3 emails", 3),
    ),
)
def test_email_agent_builds_bounded_inbox_inspection_plan(
    instruction: str,
    expected_limit: int,
) -> None:
    plan = EmailAgent().plan(context(instruction))

    assert plan.open_questions == ()
    assert plan.requires_confirmation is False
    assert len(plan.steps) == 1
    assert plan.metadata["skill_id"] == "email.inspect_inbox"

    step = plan.steps[0]

    assert step.tool_reference.tool_id == "email"
    assert step.tool_reference.operation_id == "list_messages"
    assert step.requires_confirmation is False
    assert step.operation_input == EmailListMessagesInput(limit=expected_limit)


def test_email_agent_rejects_inbox_limit_above_native_boundary() -> None:
    plan = EmailAgent().plan(context("Muéstrame los últimos 50 correos"))

    assert plan.steps == ()
    assert plan.requires_confirmation is False
    assert plan.metadata["skill_id"] == "email.inspect_inbox"
    assert plan.open_questions == (
        "How many inbox messages should be inspected? "
        "The supported limit is between 1 and 20.",
    )


def test_email_agent_keeps_draft_requests_on_draft_skill() -> None:
    plan = EmailAgent().plan(
        context(
            "Prepara un correo para claudio@aisosu.fi "
            "asunto: Prueba Cauco "
            "cuerpo: Este es un borrador."
        )
    )

    assert plan.metadata["skill_id"] == "email.prepare_draft"
    assert plan.requires_confirmation is True
    assert plan.steps[0].tool_reference.operation_id == "draft"
