from fastapi import APIRouter, HTTPException, Request

from cauco_core.agents.review_store import PlanReviewNotFoundError

router = APIRouter(prefix="/api/cognitive-cycles", tags=["cognitive-cycles"])


@router.get("/reviews/{review_id}")
def get_cognitive_cycle(review_id: str, request: Request) -> dict:
    try:
        snapshot = request.app.state.cognitive_cycle_resolver.resolve(review_id)
    except PlanReviewNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    return {
        "review_id": snapshot.review_id,
        "current_stage": snapshot.current_stage,
        "overall_cycle_status": snapshot.overall_status,
        "blocked": snapshot.blocked,
        "terminal": snapshot.terminal,
        "awaiting_human_action": snapshot.awaiting_human_action,
        "next_permitted_action": snapshot.next_permitted_action,
        "safe_endpoint": snapshot.safe_endpoint,
        "related_record_ids": dict(snapshot.related_record_ids),
        "candidate_counts": dict(snapshot.candidate_counts),
        "proposal_counts": dict(snapshot.proposal_counts),
        "warnings": list(snapshot.warnings),
        "limitations": list(snapshot.limitations),
        "method": snapshot.method,
    }
