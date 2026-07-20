from dataclasses import dataclass

from cauco_agents import AgentPlan, GitAddInput, GitCommitInput, GitPushInput
from cauco_tools import ToolAdapterRegistry, ToolExecutionError, ToolRegistry
from cauco_tools.adapters import GitAddAdapter, GitCommitAdapter, GitPushAdapter


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
        blocking_reasons: tuple[str, ...] = ()
        if (
            reference.tool_id == "git"
            and reference.operation_id == "add"
            and isinstance(step.operation_input, GitAddInput)
            and adapter_registry
            and adapter_available
        ):
            adapter = adapter_registry.get("git", "add")
            if isinstance(adapter, GitAddAdapter):
                try:
                    adapter.inspect(step.operation_input.paths)
                except ToolExecutionError as error:
                    blocking_reasons = (error.safe_message,)
        if (
            reference.tool_id == "git"
            and reference.operation_id == "push"
            and isinstance(step.operation_input, GitPushInput)
            and adapter_registry
            and adapter_available
        ):
            adapter = adapter_registry.get("git", "push")
            if isinstance(adapter, GitPushAdapter):
                try:
                    adapter.inspect_push(step.operation_input)
                except ToolExecutionError as error:
                    blocking_reasons = (error.safe_message,)
        if (
            reference.tool_id == "git"
            and reference.operation_id == "commit"
            and isinstance(step.operation_input, GitCommitInput)
            and adapter_registry
            and adapter_available
        ):
            adapter = adapter_registry.get("git", "commit")
            if isinstance(adapter, GitCommitAdapter):
                try:
                    adapter.inspect_commit(
                        step.operation_input.message, step.operation_input.expected_staged_paths
                    )
                except ToolExecutionError as error:
                    blocking_reasons = (error.safe_message,)
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
