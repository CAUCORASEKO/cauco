from typing import Any

from fastapi import APIRouter, Query, Request
from pydantic import BaseModel

router = APIRouter(prefix="/api/learning-guidance", tags=["learning-guidance"])


class LearningGuidanceResponse(BaseModel):
    guidance: list[dict[str, Any]]
    count: int
    method: str
    limitations: list[str]


@router.get("", response_model=LearningGuidanceResponse)
def get_learning_guidance(
    request: Request,
    instruction: str = Query(..., min_length=1, max_length=4000),
    intent: str | None = Query(None, max_length=100),
    agent_id: str | None = Query(None, max_length=100),
    limit: int = Query(3, ge=1, le=10),
) -> LearningGuidanceResponse:
    resolver = request.app.state.learning_guidance_resolver
    guidance = resolver.resolve(instruction, intent, agent_id, limit=limit)
    return LearningGuidanceResponse(
        guidance=[
            {
                "candidate_id": g.candidate_id,
                "experience_id": g.experience_id,
                "proposal_id": g.proposal_id,
                "category": g.category,
                "lesson": g.lesson,
                "confidence": g.confidence,
                "tool_id": g.tool_id,
                "operation_id": g.operation_id,
                "step_index": g.step_index,
                "reason_selected": g.reason_selected,
                "source_reference": g.source_reference,
                "applied_at": g.applied_at.isoformat(),
            }
            for g in guidance
        ],
        count=len(guidance),
        method=resolver.METHOD,
        limitations=[
            "Deterministic, persisted applied proposals only; no embeddings or automatic mutation."
        ],
    )
