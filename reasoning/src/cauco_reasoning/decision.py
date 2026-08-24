import re
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


@dataclass(frozen=True, slots=True)
class _SignalCategory:
    name: str
    patterns: tuple[tuple[str, ...], ...]


def _normalize_instruction(value: str) -> tuple[str, ...]:
    """Return accent-insensitive, case-insensitive word tokens."""
    normalized = unicodedata.normalize("NFKD", value.casefold())
    without_accents = "".join(
        character for character in normalized if not unicodedata.combining(character)
    )
    return tuple(re.findall(r"[a-z0-9]+", without_accents))


def _patterns(*values: str) -> tuple[tuple[str, ...], ...]:
    return tuple(tuple(value.split()) for value in values)


class ReasoningRequirementResolver:
    """Classify requests deterministically using exact tokens and phrases.

    Mixed requests enter reasoning only when an explicit sequence connector
    combines a deterministic operation with an advisory transformation. Other
    mixed evidence remains undecided so the classifier does not guess.
    """

    _DETERMINISTIC_CATEGORIES = (
        _SignalCategory(
            "retrieval",
            _patterns(
                "show", "list", "read", "get", "open",
                "muestra", "mostrar", "muestrame", "lista", "listar",
                "lee", "leer", "abre", "abrir",
            ),
        ),
        _SignalCategory(
            "action",
            _patterns(
                "create", "send", "update", "delete", "move", "rename",
                "crea", "crear", "envia", "enviar", "actualiza", "actualizar",
                "elimina", "eliminar", "mueve", "mover", "renombra", "renombrar",
            ),
        ),
        _SignalCategory(
            "scheduling",
            _patterns("schedule", "reschedule", "programa", "programar", "reprograma"),
        ),
    )
    _REASONING_CATEGORIES = (
        _SignalCategory(
            "analysis",
            _patterns(
                "analyze", "analyse", "analysis", "analiza", "analizar",
                "analisis", "reason", "razona", "razonar",
            ),
        ),
        _SignalCategory(
            "comparison",
            _patterns(
                "compare", "comparison", "pros and cons", "which is better",
                "compara", "comparar", "comparacion", "pros y contras",
                "cual es mejor",
            ),
        ),
        _SignalCategory(
            "evaluation",
            _patterns("evaluate", "evaluation", "evalua", "evaluar", "evaluacion"),
        ),
        _SignalCategory(
            "explanation",
            _patterns(
                "explain", "explain why", "why did", "why is",
                "explica", "explicar", "explica por que", "por que",
            ),
        ),
        _SignalCategory(
            "recommendation",
            _patterns(
                "recommend", "recommendation", "best option",
                "recomienda", "recomendar", "recomendacion", "mejor opcion",
            ),
        ),
        _SignalCategory(
            "summarization",
            _patterns(
                "summarize", "summarise", "summary", "resume", "resumir",
                "resumelo", "resumelos", "sintetiza", "sintetizar",
            ),
        ),
    )
    _SEQUENCE_CONNECTORS = frozenset({"and", "then", "y", "luego"})

    def resolve(self, request: ReasoningRequest) -> ReasoningDecision:
        tokens = _normalize_instruction(request.instruction)
        deterministic = self._matched_categories(tokens, self._DETERMINISTIC_CATEGORIES)
        reasoning = self._matched_categories(tokens, self._REASONING_CATEGORIES)

        if reasoning and not deterministic:
            return ReasoningDecision(
                requirement=ReasoningRequirement.REASONING_REQUIRED,
                reason=f"reasoning category: {reasoning[0]}",
            )
        if deterministic and not reasoning:
            return ReasoningDecision(
                requirement=ReasoningRequirement.DETERMINISTIC,
                reason=f"deterministic category: {deterministic[0]}",
            )
        if deterministic and reasoning:
            if self._is_explicit_transformation(tokens):
                return ReasoningDecision(
                    requirement=ReasoningRequirement.REASONING_REQUIRED,
                    reason=(
                        "mixed request requires reasoning: "
                        f"{deterministic[0]} + {reasoning[0]}"
                    ),
                )
            return ReasoningDecision(
                requirement=ReasoningRequirement.UNDECIDED,
                reason="mixed request has no explicit transformation sequence",
            )
        return ReasoningDecision(
            requirement=ReasoningRequirement.UNDECIDED,
            reason="no recognized reasoning requirement signal",
        )

    @classmethod
    def _is_explicit_transformation(cls, tokens: tuple[str, ...]) -> bool:
        return bool(cls._SEQUENCE_CONNECTORS.intersection(tokens))

    @classmethod
    def _matched_categories(
        cls,
        tokens: tuple[str, ...],
        categories: tuple[_SignalCategory, ...],
    ) -> tuple[str, ...]:
        return tuple(
            category.name
            for category in categories
            if any(cls._contains_pattern(tokens, pattern) for pattern in category.patterns)
        )

    @staticmethod
    def _contains_pattern(tokens: tuple[str, ...], pattern: tuple[str, ...]) -> bool:
        width = len(pattern)
        return any(
            tokens[index : index + width] == pattern
            for index in range(len(tokens) - width + 1)
        )
