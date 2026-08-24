import unicodedata
from dataclasses import dataclass
from enum import StrEnum

from cauco_reasoning.models import ReasoningRequest


class ReasoningRequirement(StrEnum):
    """Whether a request should enter Cauco's reasoning layer."""

    DETERMINISTIC = "deterministic"
    REASONING_REQUIRED = "reasoning_required"
    UNDECIDED = "undecided"


@dataclass(frozen=True, slots=True)
class ReasoningDecision:
    """Deterministic decision about whether reasoning is required."""

    requirement: ReasoningRequirement
    reason: str

    def __post_init__(self) -> None:
        if not self.reason.strip():
            raise ValueError("Reasoning decision reason cannot be empty.")


def _normalize_instruction(value: str) -> str:
    """Normalize natural-language text for deterministic signal matching."""
    normalized = unicodedata.normalize("NFKD", value.casefold())
    return "".join(character for character in normalized if not unicodedata.combining(character))


class ReasoningRequirementResolver:
    """Classify requests without invoking a language model."""

    _REASONING_SIGNALS = (
        "evalua",
        "analyze",
        "analyse",
        "compare",
        "evaluate",
        "explain why",
        "recommend",
        "summarize",
        "reason",
        "analiza",
        "analizar",
        "compara",
        "comparar",
        "evaluar",
        "explica por que",
        "recomienda",
        "recomendar",
        "resume",
        "resumir",
    )

    _DETERMINISTIC_SIGNALS = (
        "list",
        "show",
        "get",
        "open",
        "read",
        "create",
        "send",
        "delete",
        "move",
        "rename",
        "lista",
        "listar",
        "muestra",
        "mostrar",
        "abre",
        "abrir",
        "lee",
        "leer",
        "crea",
        "crear",
        "envia",
        "enviar",
        "elimina",
        "eliminar",
        "mueve",
        "mover",
        "renombra",
        "renombrar",
    )

    def resolve(self, request: ReasoningRequest) -> ReasoningDecision:
        instruction = _normalize_instruction(request.instruction)

        reasoning_matches = self._matches(instruction, self._REASONING_SIGNALS)
        deterministic_matches = self._matches(
            instruction,
            self._DETERMINISTIC_SIGNALS,
        )

        if reasoning_matches and not deterministic_matches:
            return ReasoningDecision(
                requirement=ReasoningRequirement.REASONING_REQUIRED,
                reason=f"reasoning signal: {reasoning_matches[0]}",
            )

        if deterministic_matches and not reasoning_matches:
            return ReasoningDecision(
                requirement=ReasoningRequirement.DETERMINISTIC,
                reason=f"deterministic signal: {deterministic_matches[0]}",
            )

        if reasoning_matches and deterministic_matches:
            return ReasoningDecision(
                requirement=ReasoningRequirement.UNDECIDED,
                reason="request contains both deterministic and reasoning signals",
            )

        return ReasoningDecision(
            requirement=ReasoningRequirement.UNDECIDED,
            reason="no recognized reasoning requirement signal",
        )

    @staticmethod
    def _matches(instruction: str, signals: tuple[str, ...]) -> tuple[str, ...]:
        return tuple(signal for signal in signals if signal in instruction)
