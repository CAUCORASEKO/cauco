from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, Query, Request, status

from cauco_core.agents.review_store import (
    PlanReviewIntegrityError,
    PlanReviewNotFoundError,
)
from cauco_core.verification.models import (
    VerificationCapacityError,
    VerificationConflictError,
    VerificationNotFoundError,
    VerificationOutcome,
    VerificationRecord,
    VerificationValidationError,
)

router = APIRouter(prefix="/api/verifications", tags=["verifications"])


@router.post(
    "/reviews/{review_id}",
    status_code=status.HTTP_201_CREATED,
)
def verify_review(review_id: str, request: Request) -> dict[str, Any]:
    try:
        record = request.app.state.verification_service.verify(review_id)
        return record_response(record)
    except PlanReviewNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(error),
        ) from error
    except (
        PlanReviewIntegrityError,
        VerificationConflictError,
        VerificationCapacityError,
    ) as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(error),
        ) from error
    except VerificationValidationError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(error),
        ) from error


@router.get("")
def list_verifications(
    request: Request,
    review_id: Annotated[str | None, Query(max_length=100)] = None,
    outcome: VerificationOutcome | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> dict[str, Any]:
    records = request.app.state.verification_store.list(
        review_id=review_id,
        outcome=outcome,
        limit=limit,
    )
    return {
        "verifications": [record_response(record) for record in records],
        "count": len(records),
    }


@router.get("/executions/{execution_id}")
def get_verification_for_execution(
    execution_id: str,
    request: Request,
) -> dict[str, Any]:
    try:
        record = request.app.state.verification_store.for_execution(execution_id)
        return record_response(record)
    except VerificationNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(error),
        ) from error


@router.get("/{verification_id}")
def get_verification(
    verification_id: str,
    request: Request,
) -> dict[str, Any]:
    try:
        record = request.app.state.verification_store.get(verification_id)
        return record_response(record)
    except VerificationNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(error),
        ) from error


def record_response(record: VerificationRecord) -> dict[str, Any]:
    return {
        "verification_id": record.verification_id,
        "execution_id": record.execution_id,
        "review_id": record.review_id,
        "snapshot_digest": record.snapshot_digest,
        "created_at": record.created_at.isoformat(),
        "outcome": record.outcome.value,
        "recommendation": record.recommendation.value,
        "method": record.method,
        "step_results": [
            {
                "step_index": step.step_index,
                "tool_id": step.tool_id,
                "operation_id": step.operation_id,
                "outcome": step.outcome.value,
                "method": step.method,
                "expected_conditions": list(step.expected_conditions),
                "observed_conditions": list(step.observed_conditions),
                "evidence_references": list(step.evidence_references),
                "deviations": list(step.deviations),
                "unresolved_conditions": list(step.unresolved_conditions),
                "rollback_available": step.rollback_available,
            }
            for step in record.step_results
        ],
        "evidence_references": list(record.evidence_references),
        "deviations": list(record.deviations),
        "unresolved_conditions": list(record.unresolved_conditions),
        "rollback_available": record.rollback_available,
        "metadata": dict(record.metadata),
    }
