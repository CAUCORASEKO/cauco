import re

from cauco_core.learning_guidance.models import LearningGuidance
from cauco_core.memory_candidates.models import (
    MemoryCandidateDisposition,
    MemoryCandidateStatus,
    MemoryCandidateTarget,
)
from cauco_core.memory_candidates.store import MemoryCandidateStore
from cauco_core.memory_writing.models import MemoryWriteProposalState
from cauco_core.memory_writing.store import MemoryWriteProposalStore


class LearningGuidanceResolver:
    METHOD = "deterministic_applied_learning_guidance_v1"

    def __init__(
        self,
        candidate_store: MemoryCandidateStore,
        proposal_store: MemoryWriteProposalStore,
        *,
        max_items: int = 3,
    ):
        self.candidate_store = candidate_store
        self.proposal_store = proposal_store
        self.max_items = max_items

    def resolve(
        self,
        instruction: str,
        resolved_intent: str | None = None,
        selected_agent_id: str | None = None,
        *,
        tool_id: str | None = None,
        operation_id: str | None = None,
        limit: int | None = None,
    ) -> tuple[LearningGuidance, ...]:
        if limit is not None and not 1 <= limit <= 10:
            raise ValueError("Learning guidance limit must be between 1 and 10.")
        terms = set(_terms(f"{instruction} {resolved_intent or ''}"))
        result: list[tuple[tuple[int, int, float, float, str], LearningGuidance]] = []
        for stored in self.proposal_store.list(
            state=MemoryWriteProposalState.APPLIED, source_type="memory_candidate", limit=100
        ):
            candidate_id = stored.proposal.source_id
            if not candidate_id:
                continue
            try:
                candidate = self.candidate_store.get(candidate_id)
            except Exception:
                continue
            if not (
                candidate.status is MemoryCandidateStatus.APPROVED
                and candidate.disposition is MemoryCandidateDisposition.PROMOTE_TO_MEMORY
                and candidate.target is MemoryCandidateTarget.LEARNING
            ):
                continue
            lesson = candidate.lesson
            exact = bool(
                tool_id
                and operation_id
                and lesson.tool_id == tool_id
                and lesson.operation_id == operation_id
            )
            tool_match = bool(tool_id and lesson.tool_id == tool_id)
            operation_match = bool(operation_id and lesson.operation_id == operation_id)
            match_rank = 2 if exact else 1 if tool_match or operation_match else 0
            overlap = len(terms & set(_terms(f"{lesson.observation} {lesson.lesson}")))
            if match_rank == 0 and overlap == 0 and lesson.category.value != "planning":
                continue
            reason = (
                "Exact tool/operation match."
                if exact
                else (
                    "Relevant tool or operation match."
                    if tool_match or operation_match
                    else (
                        "Relevant lesson terms matched the request."
                        if overlap
                        else "Planning-category guidance selected for planning context."
                    )
                )
            )
            guidance = LearningGuidance(
                candidate.candidate_id,
                candidate.experience_id,
                stored.proposal.proposal_id,
                lesson.category.value,
                lesson.lesson,
                lesson.confidence,
                lesson.tool_id,
                lesson.operation_id,
                lesson.step_index,
                reason,
                f"memory_candidate:{candidate.candidate_id};proposal:{stored.proposal.proposal_id}",
                stored.applied_at or stored.created_at,
            )
            result.append(
                (
                    (
                        -match_rank,
                        -overlap,
                        -lesson.confidence,
                        -(stored.applied_at or stored.created_at).timestamp(),
                        candidate.candidate_id,
                    ),
                    guidance,
                )
            )
        result.sort(key=lambda item: item[0])
        return tuple(item[1] for item in result[: limit or self.max_items])


def _terms(value: str) -> tuple[str, ...]:
    return tuple(
        dict.fromkeys(
            term for term in re.findall(r"[a-z0-9_]+", value.casefold()) if len(term) >= 4
        )
    )
