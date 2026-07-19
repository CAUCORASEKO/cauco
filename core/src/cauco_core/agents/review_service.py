from cauco_agents import AgentContextRequest, AgentPlanReviewRecord

from cauco_core.agents.planning import AgentPlanningService
from cauco_core.agents.review_store import AgentPlanReviewStore


class PlanReviewNoMatchError(ValueError):
    pass


class AgentPlanReviewService:
    def __init__(
        self,
        planning_service: AgentPlanningService,
        review_store: AgentPlanReviewStore,
    ) -> None:
        self.planning_service = planning_service
        self.review_store = review_store

    def create(
        self,
        request: AgentContextRequest,
        *,
        ttl_seconds: int | None = None,
    ) -> AgentPlanReviewRecord:
        outcome = self.planning_service.plan(request)
        if (
            outcome.routing.selected_agent_id is None
            or outcome.context is None
            or outcome.plan is None
        ):
            raise PlanReviewNoMatchError(
                "No agent met the routing threshold for plan review creation."
            )
        return self.review_store.create(
            instruction=request.instruction,
            routing=outcome.routing,
            context=outcome.context,
            plan=outcome.plan,
            ttl_seconds=ttl_seconds,
        )
