from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, Query, Request, status

from cauco_core.learning.models import (
    ExperienceCapacityError,
    ExperienceConflictError,
    ExperienceNotFoundError,
    ExperienceOutcome,
    ExperienceRecord,
)
from cauco_core.verification.models import VerificationNotFoundError

router = APIRouter(prefix="/api/experiences", tags=["experiences"])


@router.post("/verifications/{verification_id}", status_code=status.HTTP_201_CREATED)
def consolidate(verification_id: str, request: Request) -> dict[str, Any]:
    try:
        return record_response(
            request.app.state.experience_consolidation_service.consolidate(verification_id)
        )
    except VerificationNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except (ExperienceConflictError, ExperienceCapacityError) as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@router.get("")
def list_experiences(
    request: Request,
    review_id: Annotated[str | None, Query(max_length=100)] = None,
    outcome: ExperienceOutcome | None = None,
    memory_candidate: bool | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> dict[str, Any]:
    records = request.app.state.experience_store.list(
        review_id=review_id, outcome=outcome, memory_candidate=memory_candidate, limit=limit
    )
    return {"experiences": [record_response(record) for record in records], "count": len(records)}


@router.get("/verifications/{verification_id}")
def get_for_verification(verification_id: str, request: Request) -> dict[str, Any]:
    try:
        return record_response(request.app.state.experience_store.for_verification(verification_id))
    except ExperienceNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@router.get("/{experience_id}")
def get_experience(experience_id: str, request: Request) -> dict[str, Any]:
    try:
        return record_response(request.app.state.experience_store.get(experience_id))
    except ExperienceNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


def record_response(record: ExperienceRecord) -> dict[str, Any]:
    return {
        "experience_id": record.experience_id,
        "verification_id": record.verification_id,
        "execution_id": record.execution_id,
        "review_id": record.review_id,
        "snapshot_digest": record.snapshot_digest,
        "created_at": record.created_at.isoformat(),
        "outcome": record.outcome.value,
        "summary": record.summary,
        "lesson_candidates": [
            {
                "category": item.category.value,
                "observation": item.observation,
                "lesson": item.lesson,
                "confidence": item.confidence,
                "reusable": item.reusable,
                "tool_id": item.tool_id,
                "operation_id": item.operation_id,
                "step_index": item.step_index,
            }
            for item in record.lesson_candidates
        ],
        "memory_candidate": record.memory_candidate,
        "recommendation": record.recommendation,
        "method": record.method,
    }
