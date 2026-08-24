from cauco_reasoning import (
    ReasoningRequest,
    ReasoningRequirement,
    ReasoningRequirementResolver,
)


def resolve(instruction: str):
    return ReasoningRequirementResolver().resolve(ReasoningRequest(instruction=instruction))


def test_simple_mail_listing_is_deterministic() -> None:
    decision = resolve("Muéstrame los últimos cinco correos")

    assert decision.requirement is ReasoningRequirement.DETERMINISTIC


def test_simple_calendar_listing_is_deterministic() -> None:
    decision = resolve("Muestra mis eventos de hoy")

    assert decision.requirement is ReasoningRequirement.DETERMINISTIC


def test_analysis_requires_reasoning() -> None:
    decision = resolve("Analiza estos correos y dime cuáles son importantes")

    assert decision.requirement is ReasoningRequirement.REASONING_REQUIRED


def test_comparison_requires_reasoning() -> None:
    decision = resolve("Compare these two project proposals")

    assert decision.requirement is ReasoningRequirement.REASONING_REQUIRED


def test_mixed_request_is_not_guessed() -> None:
    decision = resolve("Read these emails and summarize them")

    assert decision.requirement is ReasoningRequirement.UNDECIDED


def test_unknown_request_is_not_guessed() -> None:
    decision = resolve("What should I do about this?")

    assert decision.requirement is ReasoningRequirement.UNDECIDED


def test_spanish_accented_command_is_normalized() -> None:
    decision = resolve("Muéstrame mis eventos de mañana")

    assert decision.requirement is ReasoningRequirement.DETERMINISTIC


def test_spanish_reasoning_signal_with_accent_is_normalized() -> None:
    decision = resolve("Evalúa estas dos alternativas")

    assert decision.requirement is ReasoningRequirement.REASONING_REQUIRED
