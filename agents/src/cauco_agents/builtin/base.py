import re
from abc import abstractmethod

from cauco_agents.base import PlanningAgent
from cauco_agents.models import AgentContext, AgentMatch, AgentRequest, AgentResult


def normalized_signal_text(value: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", value.casefold()))


class DeterministicSignalAgent(PlanningAgent):
    signals: tuple[str, ...]

    def can_handle(self, request: AgentRequest) -> AgentMatch:
        normalized = normalized_signal_text(request.instruction)
        padded = f" {normalized} "
        matched_signals = tuple(
            signal for signal in self.signals if f" {signal} " in padded
        )
        intent_matched = (
            request.intent is not None
            and normalized_signal_text(request.intent) in self.metadata.supported_intents
        )
        score = 0
        if matched_signals:
            score = max(60 if " " in signal else 50 for signal in matched_signals)
            score += 10 * (len(matched_signals) - 1)
        if intent_matched:
            score = max(score + 15, 70)
        score = min(score, 100)
        reasoning = tuple(
            f"Matched {self.metadata.name} routing signal: {signal}."
            for signal in matched_signals
        )
        if intent_matched:
            reasoning += (f"Matched explicit intent: {request.intent}.",)
        if not reasoning:
            reasoning = (f"No {self.metadata.name} routing signals matched.",)
        return AgentMatch(
            agent_id=self.id,
            matched=score > 0,
            score=score,
            matched_signals=matched_signals,
            reasoning=reasoning,
            priority=self.metadata.priority,
        )

    def execute(self, request: AgentRequest) -> AgentResult:
        warnings = list(self.base_warnings())
        if request.allow_execution:
            warnings.append(
                "allow_execution was ignored because Phase 5A agents cannot execute actions."
            )
        return AgentResult(
            agent_id=self.id,
            agent_name=self.metadata.name,
            status="proposal_only",
            summary=self.summary(),
            proposed_actions=self.proposed_actions(),
            warnings=tuple(warnings),
            requires_confirmation=self.requires_confirmation(),
            execution_performed=False,
            metadata={"framework_phase": "5A", "routing": "deterministic"},
        )

    def base_warnings(self) -> tuple[str, ...]:
        return ("Phase 5A proposes actions only; no tools or external services were used.",)

    @abstractmethod
    def summary(self) -> str: ...

    @abstractmethod
    def proposed_actions(self) -> tuple[str, ...]: ...

    @abstractmethod
    def requires_confirmation(self) -> bool: ...

    @staticmethod
    def source_ids(context: AgentContext, *kinds: str) -> tuple[str, ...]:
        return tuple(
            reference.memory_id
            for reference in context.memory_references
            if not kinds or reference.kind in kinds
        )

    @staticmethod
    def source_names(context: AgentContext, *kinds: str) -> str:
        names = tuple(
            reference.name
            for reference in context.memory_references
            if not kinds or reference.kind in kinds
        )
        return ", ".join(names) if names else "no registered memory source"
