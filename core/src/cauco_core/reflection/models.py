from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType


@dataclass(frozen=True, slots=True)
class ReflectionSummary:
    approved_candidates: int
    applied_learning_proposals: int
    planning: int
    execution: int
    verification: int


@dataclass(frozen=True, slots=True)
class ReflectionPattern:
    category: str
    lesson: str
    count: int


@dataclass(frozen=True, slots=True)
class ReflectionReport:
    summary: ReflectionSummary
    patterns: tuple[ReflectionPattern, ...]
    method: str
    limitations: tuple[str, ...]

    def as_mapping(self) -> Mapping[str, object]:
        return MappingProxyType(
            {
                "summary": self.summary,
                "patterns": self.patterns,
                "method": self.method,
                "limitations": self.limitations,
            }
        )
