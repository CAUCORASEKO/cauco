from typing import Any

from fastapi import APIRouter, Request
from pydantic import BaseModel

router = APIRouter(prefix="/api/reflection", tags=["reflection"])


class ReflectionResponse(BaseModel):
    summary: dict[str, int]
    patterns: list[dict[str, Any]]
    method: str
    limitations: list[str]


@router.get("", response_model=ReflectionResponse)
def get_reflection(request: Request) -> ReflectionResponse:
    report = request.app.state.reflection_resolver.resolve()
    return ReflectionResponse(
        summary={
            "approved_candidates": report.summary.approved_candidates,
            "applied_learning_proposals": report.summary.applied_learning_proposals,
            "planning": report.summary.planning,
            "execution": report.summary.execution,
            "verification": report.summary.verification,
        },
        patterns=[
            {"category": item.category, "lesson": item.lesson, "count": item.count}
            for item in report.patterns
        ],
        method=report.method,
        limitations=list(report.limitations),
    )
