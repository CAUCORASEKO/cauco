from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, StringConstraints

from cauco_core.memory_candidates.models import (
    MemoryCandidateCapacityError,
    MemoryCandidateConflictError,
    MemoryCandidateDisposition,
    MemoryCandidateExpiredError,
    MemoryCandidateNotFoundError,
    MemoryCandidateRecord,
    MemoryCandidateStatus,
    MemoryCandidateTarget,
    MemoryCandidateValidationError,
)
from cauco_core.memory_candidates.promotion import MemoryCandidateNotPromotableError

router = APIRouter(prefix="/api/memory-candidates", tags=["memory-candidates"])
Note = Annotated[str, StringConstraints(strip_whitespace=True, max_length=2000)]


class ReviewPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    review_note: Note | None = None


class RejectPayload(ReviewPayload):
    disposition: MemoryCandidateDisposition


def response(r: MemoryCandidateRecord) -> dict[str, Any]:
    return {
        "candidate_id": r.candidate_id,
        "experience_id": r.experience_id,
        "verification_id": r.verification_id,
        "execution_id": r.execution_id,
        "review_id": r.review_id,
        "snapshot_digest": r.snapshot_digest,
        "lesson": {
            "category": r.lesson.category.value,
            "observation": r.lesson.observation,
            "lesson": r.lesson.lesson,
            "confidence": r.lesson.confidence,
            "tool_id": r.lesson.tool_id,
            "operation_id": r.lesson.operation_id,
            "step_index": r.lesson.step_index,
        },
        "target": r.target.value,
        "status": r.status.value,
        "disposition": r.disposition.value if r.disposition else None,
        "rationale": r.rationale,
        "created_at": r.created_at.isoformat(),
        "expires_at": r.expires_at.isoformat(),
        "reviewed_at": r.reviewed_at.isoformat() if r.reviewed_at else None,
        "review_note": r.review_note,
        "method": r.method,
    }


@router.post("/experiences/{experience_id}", status_code=201)
def create(experience_id: str, request: Request) -> dict[str, Any]:
    try:
        records = request.app.state.memory_candidate_service.create_for_experience(experience_id)
        return {"candidates": [response(r) for r in records], "count": len(records)}
    except MemoryCandidateNotFoundError as e:
        raise HTTPException(404, str(e)) from e
    except MemoryCandidateValidationError as e:
        raise HTTPException(422, str(e)) from e
    except MemoryCandidateCapacityError as e:
        raise HTTPException(409, str(e)) from e


@router.get("")
def list_candidates(
    request: Request,
    experience_id: Annotated[str | None, Query(max_length=100)] = None,
    review_id: Annotated[str | None, Query(max_length=100)] = None,
    status: MemoryCandidateStatus | None = None,
    target: MemoryCandidateTarget | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
):
    records = request.app.state.memory_candidate_store.list(
        experience_id=experience_id, review_id=review_id, status=status, target=target, limit=limit
    )
    return {"candidates": [response(r) for r in records], "count": len(records)}


@router.get("/experiences/{experience_id}")
def by_experience(experience_id: str, request: Request):
    return {
        "candidates": [
            response(r)
            for r in request.app.state.memory_candidate_store.for_experience(experience_id)
        ]
    }


@router.get("/{candidate_id}")
def get(candidate_id: str, request: Request):
    try:
        return response(request.app.state.memory_candidate_store.get(candidate_id))
    except MemoryCandidateNotFoundError as e:
        raise HTTPException(404, str(e)) from e


@router.post("/{candidate_id}/approve")
def approve(candidate_id: str, payload: ReviewPayload, request: Request):
    try:
        return response(
            request.app.state.memory_candidate_store.approve(candidate_id, payload.review_note)
        )
    except MemoryCandidateNotFoundError as e:
        raise HTTPException(404, str(e)) from e
    except MemoryCandidateExpiredError as e:
        raise HTTPException(410, str(e)) from e
    except MemoryCandidateConflictError as e:
        raise HTTPException(409, str(e)) from e


@router.post("/{candidate_id}/promote")
def promote(candidate_id: str, request: Request):
    try:
        return request.app.state.memory_candidate_promotion_service.promote(candidate_id)
    except MemoryCandidateNotFoundError as e:
        raise HTTPException(404, str(e)) from e
    except MemoryCandidateExpiredError as e:
        raise HTTPException(410, str(e)) from e
    except MemoryCandidateNotPromotableError as e:
        raise HTTPException(409, str(e)) from e
    except ValueError as e:
        raise HTTPException(422, "The memory candidate data is invalid.") from e


@router.post("/{candidate_id}/reject")
def reject(candidate_id: str, payload: RejectPayload, request: Request):
    try:
        return response(
            request.app.state.memory_candidate_store.reject(
                candidate_id, payload.disposition, payload.review_note
            )
        )
    except MemoryCandidateNotFoundError as e:
        raise HTTPException(404, str(e)) from e
    except MemoryCandidateExpiredError as e:
        raise HTTPException(410, str(e)) from e
    except MemoryCandidateConflictError as e:
        raise HTTPException(409, str(e)) from e
    except ValueError as e:
        raise HTTPException(422, str(e)) from e
