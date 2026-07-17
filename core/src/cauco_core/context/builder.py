from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime

from cauco_core.context.analyzer import IntentAnalyzer
from cauco_core.context.models import ContextIntent, ContextPackage
from cauco_core.memory.engine import MemoryEngine
from cauco_core.memory.models import MemoryKind, MemoryLayer, MemoryObjectSummary


@dataclass(frozen=True)
class SelectionRule:
    layers: tuple[MemoryLayer, ...]
    kinds: tuple[MemoryKind, ...]
    reasons: tuple[str, ...]


SELECTION_RULES = {
    ContextIntent.PLANNING: SelectionRule(
        layers=(MemoryLayer.WORKING, MemoryLayer.LONG_TERM),
        kinds=(MemoryKind.TASKS, MemoryKind.PROJECTS),
        reasons=(
            "Selected Working Memory for current actions.",
            "Added Tasks.",
            "Added Projects for active context.",
        ),
    ),
    ContextIntent.PROJECT: SelectionRule(
        layers=(MemoryLayer.LONG_TERM, MemoryLayer.WORKING),
        kinds=(MemoryKind.PROJECTS, MemoryKind.TASKS),
        reasons=("Added Projects.", "Added Tasks for current project actions."),
    ),
    ContextIntent.DECISION: SelectionRule(
        layers=(MemoryLayer.LONG_TERM, MemoryLayer.GOVERNANCE),
        kinds=(MemoryKind.DECISIONS, MemoryKind.RULES, MemoryKind.PROJECTS),
        reasons=(
            "Added Decisions for recorded rationale.",
            "Added Memory Rules for governance context.",
            "Added Projects for decision context.",
        ),
    ),
    ContextIntent.RELATIONSHIP: SelectionRule(
        layers=(MemoryLayer.LONG_TERM,),
        kinds=(MemoryKind.RELATIONSHIPS,),
        reasons=("Added Relationships for known people and connections.",),
    ),
    ContextIntent.RESEARCH: SelectionRule(
        layers=(MemoryLayer.LONG_TERM,),
        kinds=(MemoryKind.RESEARCH, MemoryKind.REPORTS, MemoryKind.DECISIONS),
        reasons=("Added Research.", "Added Reports and Decisions for supporting context."),
    ),
    ContextIntent.MEETING: SelectionRule(
        layers=(MemoryLayer.WORKING, MemoryLayer.LONG_TERM),
        kinds=(MemoryKind.MEETINGS, MemoryKind.PROJECTS, MemoryKind.TASKS),
        reasons=("Added Meetings.", "Added Projects and Tasks for meeting context."),
    ),
    ContextIntent.REPORT: SelectionRule(
        layers=(MemoryLayer.LONG_TERM,),
        kinds=(MemoryKind.REPORTS, MemoryKind.PROJECTS, MemoryKind.DECISIONS),
        reasons=("Added Reports.", "Added Projects and Decisions for report context."),
    ),
    ContextIntent.IDENTITY: SelectionRule(
        layers=(MemoryLayer.IDENTITY,),
        kinds=(MemoryKind.IDENTITY,),
        reasons=("Added Identity Memory.",),
    ),
    ContextIntent.GENERAL: SelectionRule(
        layers=(MemoryLayer.LONG_TERM,),
        kinds=(MemoryKind.GENERAL,),
        reasons=("Used General Memory because no specific intent matched.",),
    ),
}


class ContextBuilder:
    def __init__(
        self,
        memory_engine: MemoryEngine,
        analyzer: IntentAnalyzer | None = None,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.memory_engine = memory_engine
        self.analyzer = analyzer or IntentAnalyzer()
        self.clock = clock or (lambda: datetime.now(tz=UTC))

    def build(self, question: str) -> ContextPackage:
        normalized_question = question.strip()
        analysis = self.analyzer.analyze(normalized_question)
        rule = SELECTION_RULES[analysis.intent]
        selected = [
            memory
            for memory in self.memory_engine.list_objects()
            if memory.kind in rule.kinds and memory.layer in rule.layers
        ]
        reasoning = [self._intent_reason(analysis.intent, analysis.matched_keywords)]
        reasoning.extend(rule.reasons)
        if not selected:
            reasoning.append("No classified memory objects matched the selection rules.")
        return ContextPackage(
            question=normalized_question,
            detected_intent=analysis.intent,
            selected_layers=list(rule.layers),
            selected_kinds=list(rule.kinds),
            selected_memory_objects=[MemoryObjectSummary.from_object(item) for item in selected],
            reasoning=reasoning,
            generated_at=self.clock(),
        )

    @staticmethod
    def _intent_reason(intent: ContextIntent, matches: list[str]) -> str:
        if not matches:
            return "Detected general intent because no deterministic intent rule matched."
        return f"Detected {intent.value} intent from: {', '.join(matches)}."
