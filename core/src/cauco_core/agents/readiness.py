from dataclasses import asdict, dataclass, is_dataclass

from cauco_agents import AgentPlan, contains_step_output_binding
from cauco_tools import ToolAdapterRegistry, ToolExecutionError, ToolExecutionRequest, ToolRegistry


@dataclass(frozen=True, slots=True)
class PlanToolReadiness:
    tool_id: str
    operation_id: str
    target: str | None
    registered: bool
    enabled: bool
    safe: bool | None
    confirmation_required: bool | None
    operation_exists: bool
    runtime_execution_allowed: bool
    adapter_available: bool
    executable_now: bool
    mutation_confirmation_required: bool
    preview_required: bool
    blocking_reasons: tuple[str, ...] = ()
    execution_enabled: bool = False


@dataclass(frozen=True, slots=True)
class AgentPlanReadiness:
    ready: bool
    references: tuple[PlanToolReadiness, ...]
    execution_enabled: bool = False


class PlanValidator:
    """Generic, non-mutating validator for ExecutionPlan v1."""

    def __init__(
        self, registry: ToolRegistry, adapter_registry: ToolAdapterRegistry | None = None
    ) -> None:
        self.registry = registry
        self.adapter_registry = adapter_registry

    def validate(self, plan: AgentPlan) -> AgentPlanReadiness:
        return evaluate_plan_readiness(plan, self.registry, self.adapter_registry)


def evaluate_plan_readiness(
    plan: AgentPlan,
    registry: ToolRegistry,
    adapter_registry: ToolAdapterRegistry | None = None,
) -> AgentPlanReadiness:
    references: list[PlanToolReadiness] = []
    for step in plan.steps:
        reference = step.tool_reference
        if reference is None:
            continue
        validation = registry.validate(reference.tool_id, reference.operation_id)
        adapter_available = bool(
            adapter_registry and adapter_registry.exists(reference.tool_id, reference.operation_id)
        )
        blocking: list[str] = []
        if not validation.tool_exists:
            blocking.append(validation.reason or "Tool is not registered.")
        elif not validation.operation_exists:
            blocking.append(validation.reason or "Operation is not registered.")
        if adapter_registry and adapter_available:
            adapter = adapter_registry.get(reference.tool_id, reference.operation_id)
            preflight = getattr(adapter, "preflight", None)
            if callable(preflight) and not contains_step_output_binding(step.operation_input):
                arguments = (
                    asdict(step.operation_input) if is_dataclass(step.operation_input) else {}
                )
                try:
                    preflight(
                        ToolExecutionRequest(reference.tool_id, reference.operation_id, arguments)
                    )
                except ToolExecutionError as error:
                    blocking.append(error.safe_message)
        blocking_reasons = tuple(blocking)
        references.append(
            PlanToolReadiness(
                tool_id=reference.tool_id,
                operation_id=reference.operation_id,
                target=reference.target,
                registered=validation.tool_exists and validation.operation_exists,
                enabled=validation.valid,
                safe=validation.safe,
                confirmation_required=validation.confirmation_required,
                operation_exists=validation.operation_exists,
                runtime_execution_allowed=validation.runtime_execution_allowed,
                adapter_available=adapter_available,
                executable_now=(
                    validation.valid
                    and validation.runtime_execution_allowed
                    and adapter_available
                    and not validation.preview_required
                ),
                mutation_confirmation_required=validation.mutation,
                preview_required=validation.preview_required,
                blocking_reasons=blocking_reasons,
            )
        )
    return AgentPlanReadiness(
        ready=bool(references)
        and all(
            item.registered and item.enabled and not item.blocking_reasons for item in references
        ),
        references=tuple(references),
    )
