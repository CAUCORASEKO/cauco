from collections.abc import Mapping, Sequence
from dataclasses import fields, is_dataclass, replace
from typing import Any

from cauco_agents import StepOutputBinding

from cauco_core.execution.models import (
    AgentPlanExecutionRecord,
    StepExecutionStatus,
)


class StepOutputBindingError(ValueError):
    def __init__(
        self,
        message: str,
        *,
        binding: StepOutputBinding,
        destination_field: str,
    ) -> None:
        super().__init__(message)
        self.binding = binding
        self.destination_field = destination_field


def resolve_step_output_bindings(
    operation_input: object,
    *,
    record: AgentPlanExecutionRecord,
    consuming_step_index: int,
) -> tuple[object, tuple[tuple[str, StepOutputBinding], ...]]:
    resolved, resolutions = _resolve_value(
        operation_input,
        record=record,
        consuming_step_index=consuming_step_index,
        destination_field="operation_input",
    )
    return resolved, tuple(resolutions)


def _resolve_value(
    value: Any,
    *,
    record: AgentPlanExecutionRecord,
    consuming_step_index: int,
    destination_field: str,
) -> tuple[Any, list[tuple[str, StepOutputBinding]]]:
    if isinstance(value, StepOutputBinding):
        resolved = _resolve_binding(
            value,
            record=record,
            consuming_step_index=consuming_step_index,
            destination_field=destination_field,
        )
        return resolved, [(destination_field, value)]

    if is_dataclass(value) and not isinstance(value, type):
        updates: dict[str, Any] = {}
        resolutions: list[tuple[str, StepOutputBinding]] = []
        for item in fields(value):
            field_name = (
                item.name
                if destination_field == "operation_input"
                else f"{destination_field}.{item.name}"
            )
            resolved, nested = _resolve_value(
                getattr(value, item.name),
                record=record,
                consuming_step_index=consuming_step_index,
                destination_field=field_name,
            )
            updates[item.name] = resolved
            resolutions.extend(nested)
        if not resolutions:
            return value, []
        try:
            return replace(value, **updates), resolutions
        except (TypeError, ValueError) as error:
            binding = resolutions[0][1]
            raise StepOutputBindingError(
                "Resolved output does not satisfy the approved typed operation input.",
                binding=binding,
                destination_field=resolutions[0][0],
            ) from error

    if isinstance(value, tuple):
        resolved_items: list[Any] = []
        resolutions: list[tuple[str, StepOutputBinding]] = []
        for index, item in enumerate(value):
            resolved, nested = _resolve_value(
                item,
                record=record,
                consuming_step_index=consuming_step_index,
                destination_field=f"{destination_field}[{index}]",
            )
            resolved_items.append(resolved)
            resolutions.extend(nested)
        return tuple(resolved_items), resolutions

    if isinstance(value, Mapping):
        resolved_mapping: dict[str, Any] = {}
        resolutions: list[tuple[str, StepOutputBinding]] = []
        for key, item in value.items():
            resolved, nested = _resolve_value(
                item,
                record=record,
                consuming_step_index=consuming_step_index,
                destination_field=f"{destination_field}.{key}",
            )
            resolved_mapping[str(key)] = resolved
            resolutions.extend(nested)
        return resolved_mapping, resolutions

    return value, []


def _resolve_binding(
    binding: StepOutputBinding,
    *,
    record: AgentPlanExecutionRecord,
    consuming_step_index: int,
    destination_field: str,
) -> object:
    if binding.source_step_index >= consuming_step_index:
        raise StepOutputBindingError(
            "Output bindings must reference an earlier step.",
            binding=binding,
            destination_field=destination_field,
        )

    source = next(
        (step for step in record.step_records if step.step_index == binding.source_step_index),
        None,
    )
    if source is None:
        raise StepOutputBindingError(
            "Output binding source step does not exist.",
            binding=binding,
            destination_field=destination_field,
        )
    if (
        source.status is not StepExecutionStatus.COMPLETED
        or source.result is None
        or not source.result.success
    ):
        raise StepOutputBindingError(
            "Output binding source step did not complete successfully.",
            binding=binding,
            destination_field=destination_field,
        )

    current: object = source.result.structured_data
    for segment in binding.path:
        if isinstance(segment, str):
            if not isinstance(current, Mapping) or segment not in current:
                raise StepOutputBindingError(
                    "Output binding mapping key does not exist.",
                    binding=binding,
                    destination_field=destination_field,
                )
            current = current[segment]
        else:
            if (
                not isinstance(current, Sequence)
                or isinstance(current, (str, bytes, bytearray))
                or segment >= len(current)
            ):
                raise StepOutputBindingError(
                    "Output binding list index is invalid.",
                    binding=binding,
                    destination_field=destination_field,
                )
            current = current[segment]

    if not _matches_type(current, binding.value_type):
        raise StepOutputBindingError(
            "Output binding resolved to the wrong scalar type.",
            binding=binding,
            destination_field=destination_field,
        )
    return current


def _matches_type(value: object, value_type: str) -> bool:
    if value_type == "string":
        return isinstance(value, str)
    if value_type == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if value_type == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if value_type == "boolean":
        return isinstance(value, bool)
    return False
