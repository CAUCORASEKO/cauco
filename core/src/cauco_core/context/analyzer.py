from dataclasses import dataclass

from cauco_core.context.models import ContextIntent, IntentAnalysis
from cauco_core.memory.classifier import normalize_signal


@dataclass(frozen=True)
class IntentRule:
    intent: ContextIntent
    keywords: tuple[str, ...]


# Ordering is the deterministic tie-breaker. Narrower identity and relationship
# phrases precede broader planning and decision language.
INTENT_RULES = (
    IntentRule(
        ContextIntent.IDENTITY,
        ("who am i", "about me", "my preferences", "my values", "identity", "personality"),
    ),
    IntentRule(
        ContextIntent.RELATIONSHIP,
        ("who is", "who are", "relationship", "relationships", "person", "people"),
    ),
    IntentRule(
        ContextIntent.PLANNING,
        (
            "what should i",
            "work on today",
            "plan my",
            "priority",
            "priorities",
            "task",
            "tasks",
            "todo",
            "today",
            "next action",
        ),
    ),
    IntentRule(
        ContextIntent.PROJECT,
        ("working on", "project", "projects", "initiative", "initiatives", "roadmap"),
    ),
    IntentRule(
        ContextIntent.DECISION,
        (
            "how does memory work",
            "why are we",
            "why did",
            "decision",
            "decisions",
            "decide",
            "decided",
            "choose",
            "chosen",
            "using",
        ),
    ),
    IntentRule(
        ContextIntent.RESEARCH,
        ("research", "investigate", "evidence", "findings", "study", "learn about"),
    ),
    IntentRule(
        ContextIntent.MEETING,
        ("meeting", "meetings", "agenda", "minutes", "standup", "sync"),
    ),
    IntentRule(
        ContextIntent.REPORT,
        ("status report", "weekly report", "report", "reports", "progress summary"),
    ),
)


class IntentAnalyzer:
    def analyze(self, question: str) -> IntentAnalysis:
        normalized = normalize_signal(question)
        best_rule: IntentRule | None = None
        best_score = 0
        best_matches: list[str] = []
        for rule in INTENT_RULES:
            matches = [keyword for keyword in rule.keywords if _contains(normalized, keyword)]
            score = sum(2 if " " in keyword else 1 for keyword in matches)
            if score > best_score:
                best_rule = rule
                best_score = score
                best_matches = matches
        if best_rule is None:
            return IntentAnalysis(
                intent=ContextIntent.GENERAL,
                score=0,
                matched_keywords=[],
            )
        return IntentAnalysis(
            intent=best_rule.intent,
            score=best_score,
            matched_keywords=best_matches,
        )

    def supported_intents(self) -> list[ContextIntent]:
        return list(ContextIntent)


def _contains(normalized_question: str, keyword: str) -> bool:
    return f" {keyword} " in f" {normalized_question} "
