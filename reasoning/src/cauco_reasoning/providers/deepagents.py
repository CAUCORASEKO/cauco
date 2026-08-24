"""Deep Agents implementation of the provider-neutral reasoning boundary."""

import logging
from collections.abc import Mapping
from dataclasses import dataclass
from threading import Lock
from typing import Any, Protocol

from cauco_reasoning.models import ReasoningRequest, ReasoningResult

logger = logging.getLogger(__name__)
_HARNESS_LOCK = Lock()
_INITIALIZED_MODELS: set[str] = set()
_EXCLUDED_TOOLS = frozenset(
    {"ls", "read_file", "write_file", "edit_file", "glob", "grep", "execute", "task"}
)


class DeepAgentsRuntime(Protocol):
    """Small runtime seam used to keep provider tests deterministic."""

    def __call__(self, *, model: str, messages: list[dict[str, str]], tools: list[Any]) -> Any: ...


def initialize_deepagents_harness(model: str) -> None:
    """Register the restricted harness once for this process and model.

    Deep Agents 0.7.8 resolves harness profiles from a process-wide registry.
    This explicit initialization therefore has a process-wide effect, but is
    idempotent and never merges a profile again for the same model.
    """
    from deepagents import (
        GeneralPurposeSubagentProfile,
        HarnessProfile,
        register_harness_profile,
    )

    with _HARNESS_LOCK:
        if model in _INITIALIZED_MODELS:
            return
        register_harness_profile(
            model,
            HarnessProfile(
                excluded_tools=_EXCLUDED_TOOLS,
                general_purpose_subagent=GeneralPurposeSubagentProfile(enabled=False),
            ),
        )
        _INITIALIZED_MODELS.add(model)


def _default_runtime(*, model: str, messages: list[dict[str, str]], tools: list[Any]) -> Any:
    """Build and invoke Deep Agents without exposing its built-in tool suite."""
    from deepagents import create_deep_agent

    initialize_deepagents_harness(model)
    agent = create_deep_agent(model=model, tools=tools)
    return agent.invoke({"messages": messages})


def _response_text(response: Any) -> str:
    if isinstance(response, str):
        return response
    if isinstance(response, Mapping):
        messages = response.get("messages", [])
        if not messages:
            return ""
        message = messages[-1]
    else:
        message = response
    content = (
        message.get("content", "")
        if isinstance(message, Mapping)
        else getattr(message, "content", "")
    )
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(
            block.get("text", "") if isinstance(block, Mapping) else getattr(block, "text", "")
            for block in content
            if (
                (isinstance(block, Mapping) and isinstance(block.get("text", ""), str))
                or (hasattr(block, "text") and isinstance(getattr(block, "text", ""), str))
            )
        )
    return ""


def _json_compatible(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _json_compatible(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_compatible(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def _response_data(response: Any) -> Mapping[str, Any]:
    if isinstance(response, Mapping):
        structured = response.get("structured_response")
        if isinstance(structured, Mapping):
            return _json_compatible(structured)
        if structured is not None:
            model_dump = getattr(structured, "model_dump", None)
            if callable(model_dump):
                dumped = model_dump()
                if isinstance(dumped, Mapping):
                    return _json_compatible(dumped)
    return {}


@dataclass(frozen=True, slots=True)
class DeepAgentsReasoningEngine:
    """Reasoning provider backed by Deep Agents, with no Cauco tools."""

    model: str
    provider_name: str = "deepagents"
    runtime: DeepAgentsRuntime = _default_runtime

    def reason(self, request: ReasoningRequest) -> ReasoningResult:
        messages = [{"role": "user", "content": self._prompt(request)}]
        try:
            response = self.runtime(model=self.model, messages=messages, tools=[])
        except Exception:
            logger.exception("Deep Agents reasoning failed for provider=%s", self.provider_name)
            return ReasoningResult(
                provider=self.provider_name,
                model=self.model,
                text="",
                structured_data={"reason": "provider_unavailable"},
                reasoning_performed=False,
            )

        return ReasoningResult(
            provider=self.provider_name,
            model=self.model,
            text=_response_text(response),
            structured_data={**_response_data(response), "agent_id": request.agent_id},
            reasoning_performed=True,
        )

    @staticmethod
    def _prompt(request: ReasoningRequest) -> str:
        context = "\n".join(f"{key}: {value}" for key, value in request.context.items())
        return (
            f"Instruction: {request.instruction}\nContext:\n{context}"
            if context
            else f"Instruction: {request.instruction}"
        )
