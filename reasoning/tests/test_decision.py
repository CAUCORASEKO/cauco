import pytest

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


def test_mixed_retrieval_and_summarization_requires_reasoning() -> None:
    decision = resolve("Read these emails and summarize them")

    assert decision.requirement is ReasoningRequirement.REASONING_REQUIRED
    assert decision.reason == "mixed request requires reasoning: retrieval + summarization"


def test_unknown_request_is_not_guessed() -> None:
    decision = resolve("What should I do about this?")

    assert decision.requirement is ReasoningRequirement.UNDECIDED


def test_spanish_accented_command_is_normalized() -> None:
    decision = resolve("Muéstrame mis eventos de mañana")

    assert decision.requirement is ReasoningRequirement.DETERMINISTIC


def test_spanish_reasoning_signal_with_accent_is_normalized() -> None:
    decision = resolve("Evalúa estas dos alternativas")

    assert decision.requirement is ReasoningRequirement.REASONING_REQUIRED


@pytest.mark.parametrize(
    "instruction",
    [
        "Show me my last five emails",
        "List tomorrow's calendar events",
        "Abre el archivo README.md",
        "Create a calendar event tomorrow at 10",
        "Send this email to Maria",
        "Read my inbox",
        "Delete this draft",
        "MUÉSTRAME LOS ÚLTIMOS CINCO CORREOS!",
    ],
)
def test_direct_operations_are_deterministic(instruction: str) -> None:
    decision = resolve(instruction)

    assert decision.requirement is ReasoningRequirement.DETERMINISTIC
    assert decision.reason.startswith("deterministic category:")


@pytest.mark.parametrize(
    ("instruction", "category"),
    [
        ("Compare these two proposals", "comparison"),
        ("Compara estas dos propuestas", "comparison"),
        ("Evaluate the alternatives", "evaluation"),
        ("Evalúa estas alternativas", "evaluation"),
        ("Analyze why this project is delayed", "analysis"),
        ("Analiza por qué este proyecto está atrasado", "analysis"),
        ("Recommend the best option", "recommendation"),
        ("Recomienda la mejor opción", "recommendation"),
        ("Explain why these results differ", "explanation"),
        ("Resume y compara estos documentos", "comparison"),
        ("Summarize these notes", "summarization"),
        ("Which is better?", "comparison"),
        ("¿Cuál es mejor?", "comparison"),
        ("Give me the pros and cons", "comparison"),
        ("Dame los pros y contras", "comparison"),
    ],
)
def test_reasoning_structures_are_phrase_aware(instruction: str, category: str) -> None:
    decision = resolve(instruction)

    assert decision.requirement is ReasoningRequirement.REASONING_REQUIRED
    assert decision.reason == f"reasoning category: {category}"


@pytest.mark.parametrize(
    "instruction",
    [
        "Lee estos correos y resúmelos",
        "Open the report and analyze the risks",
        "Abre el informe y analiza los riesgos",
        "List the proposals and compare them",
    ],
)
def test_explicit_retrieval_then_transformation_requires_reasoning(instruction: str) -> None:
    decision = resolve(instruction)

    assert decision.requirement is ReasoningRequirement.REASONING_REQUIRED
    assert decision.reason.startswith("mixed request requires reasoning:")


@pytest.mark.parametrize(
    "instruction",
    [
        "Target the next milestone",
        "The budget is reasonable",
        "This precomparison template is available",
        "The analyst sent an updated status",
        "Process this item",
        "What should I do about this?",
    ],
)
def test_signal_fragments_inside_words_do_not_match(instruction: str) -> None:
    decision = resolve(instruction)

    assert decision.requirement is ReasoningRequirement.UNDECIDED


def test_unclear_mixed_request_remains_undecided() -> None:
    decision = resolve("Do not analyze this; just list it")

    assert decision.requirement is ReasoningRequirement.UNDECIDED
