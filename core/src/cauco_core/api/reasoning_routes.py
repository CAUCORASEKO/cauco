import re
from pathlib import Path
from uuid import UUID

from cauco_agents import (
    DEFAULT_MAX_CONTEXT_ITEMS,
    DEFAULT_MAX_EXCERPT_CHARS,
    MAX_CONTEXT_ITEMS,
    MAX_EXCERPT_CHARS,
    MIN_EXCERPT_CHARS,
    AgentContextRequest,
    UnknownPreferredAgentError,
)
from cauco_agents.builtin.filesystem_agent import (
    requested_workspace_read,
    requested_workspace_write,
)
from cauco_agents.models import FilesystemWriteTextInput
from cauco_reasoning import ReasoningRequest
from cauco_tools import ToolExecutionError, ToolExecutionRequest
from cauco_tools.adapters.filesystem_mutation import FilesystemTextMutationAdapter
from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, Field, StrictBool

from cauco_core.ai.exceptions import (
    MalformedProviderResponseError,
    ModelNotFoundError,
    ProviderTimeoutError,
    ProviderUnavailableError,
)
from cauco_core.api.agent_routes import (
    AgentContextResponse,
    AgentMatchResponse,
    AgentPlanResponse,
    SelectedAgentResponse,
    context_response,
    match_response,
    plan_response,
)
from cauco_core.capability_inquiry import is_capability_inquiry
from cauco_core.execution.models import ExecutionForbiddenError, ExecutionValidationError
from cauco_core.filesystem_drafts import DraftStatus, FilesystemDraft, FilesystemDraftError
from cauco_core.reasoning import ReasoningAwarePlanningOutcome

router = APIRouter(prefix="/api/reasoning", tags=["reasoning"])


class ReasoningPlanRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    instruction: str = Field(max_length=4000)
    intent: str | None = Field(default=None, max_length=100)
    preferred_agent_id: str | None = Field(default=None, max_length=100)
    include_context: StrictBool = True
    max_context_items: int = Field(default=DEFAULT_MAX_CONTEXT_ITEMS, ge=1, le=MAX_CONTEXT_ITEMS)
    max_excerpt_chars: int = Field(
        default=DEFAULT_MAX_EXCERPT_CHARS,
        ge=MIN_EXCERPT_CHARS,
        le=MAX_EXCERPT_CHARS,
    )
    timezone: str | None = Field(default=None, min_length=1, max_length=100)
    calendar_reference: str | None = Field(default=None, min_length=17, max_length=89)
    default_event_duration_minutes: int | None = Field(default=None, ge=1, le=1440)
    mail_account_reference: str | None = Field(
        default=None,
        min_length=17,
        max_length=89,
        pattern=r"^mailacct_[A-Za-z0-9_-]{8,80}$",
    )
    mailbox_reference: str | None = Field(
        default=None,
        min_length=16,
        max_length=88,
        pattern=r"^mailbox_[A-Za-z0-9_-]{8,80}$",
    )
    use_reasoning: StrictBool = False


class ReasoningPlanningRoutingResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    selected_agent: SelectedAgentResponse | None
    match: AgentMatchResponse | None
    matches: list[AgentMatchResponse]
    preferred_agent_rejected: bool


class ReasoningPlanningDataResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: str
    routing: ReasoningPlanningRoutingResponse
    context: AgentContextResponse | None
    plan: AgentPlanResponse | None
    proposal_only: bool = True
    execution_performed: bool = False
    review_approved: bool = False
    runtime_started: bool = False


class ReasoningAwarePlanningResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reasoning_requested: bool
    reasoning_invoked: bool
    proposal_produced: bool
    proposal_validated: bool
    planning_context_enriched: bool
    provider: str | None
    model: str | None
    explanation: str
    planning: ReasoningPlanningDataResponse


class ConversationResponse(BaseModel):
    message: str
    planning_status: str
    plan: AgentPlanResponse | None
    reasoning_invoked: bool
    proposal_only: bool = True
    execution_performed: bool = False
    review_approved: bool = False
    runtime_started: bool = False
    review_id: str | None = None
    draft_id: str | None = None
    draft_status: DraftStatus | None = None
    draft_target: str | None = None
    draft_content: str | None = None
    draft_digest: str | None = None


class ConversationRequest(ReasoningPlanRequest):
    use_reasoning: StrictBool = True
    conversation_id: UUID


def _deterministic_conversation_fallback(instruction: str) -> str | None:
    normalized = " ".join(instruction.casefold().split())
    normalized = normalized.replace("’", "'").rstrip("?.!,;:")
    meta_questions = {
        "what can you do",
        "what you can do",
        "what do you do",
        "what are you able to do",
        "what can cauco do",
        "what does cauco do",
        "tell me what you can do",
        "how can you help me",
        "what can you help me with",
    }
    if normalized in meta_questions:
        return (
            "Cauco can help plan and explain tasks in an advisory way. "
            "It does not execute actions or change your system from this conversation."
        )
    return None


def _ai_conversation_fallback(request: Request, instruction: str) -> str | None:
    try:
        response = request.app.state.ai_service.chat(instruction).response.strip()
    except (
        MalformedProviderResponseError,
        ModelNotFoundError,
        ProviderTimeoutError,
        ProviderUnavailableError,
    ):
        return None
    return response or None


def _draft_response(
    draft: FilesystemDraft,
    message: str,
    status: str = "draft_active",
    *,
    executed: bool = False,
) -> ConversationResponse:
    return ConversationResponse(
        message=message,
        planning_status=status,
        plan=None,
        reasoning_invoked=False,
        proposal_only=not executed,
        execution_performed=executed,
        draft_id=draft.draft_id,
        draft_status=draft.status,
        draft_target=draft.target_relative_path,
        draft_content=draft.content,
        draft_digest=draft.digest,
    )


def _reject_draft_storage(relative: str) -> None:
    if "cauco-drafts" in {part.casefold() for part in Path(relative).parts}:
        raise HTTPException(
            status_code=403, detail="El staging de borradores es interno."
        )


def _draft_target(
    request: Request, relative: str, content: str
) -> tuple[FilesystemTextMutationAdapter, Path, str]:
    _reject_draft_storage(relative)
    policy = request.app.state.workspace_policy
    if policy is None:
        raise HTTPException(status_code=409, detail="No hay workspace configurado.")
    normalized = policy.validate_write_target(relative)
    adapter = request.app.state.tool_adapter_registry.get(
        "filesystem", "write_text_file"
    )
    if not isinstance(adapter, FilesystemTextMutationAdapter):
        raise HTTPException(
            status_code=409, detail="El adaptador filesystem no está disponible."
        )
    target, adapter_relative = adapter.resolve_target(relative)
    if normalized != adapter_relative:
        raise HTTPException(
            status_code=403, detail="Las validaciones del target no coinciden."
        )
    if len(content) > adapter.max_content_chars or "\x00" in content:
        raise HTTPException(
            status_code=400,
            detail="El contenido excede los límites de escritura segura.",
        )
    return adapter, target, normalized


def _filesystem_draft_conversation(
    payload: ConversationRequest,
    request: Request,
    write: FilesystemWriteTextInput | None,
) -> ConversationResponse | None:
    # Serialize the entire read/update/finalize sequence within this application.
    with request.app.state.filesystem_draft_lock:
        store = request.app.state.filesystem_draft_store
        if store is None:
            if write is not None:
                raise HTTPException(
                    status_code=409, detail="No hay workspace configurado."
                )
            return None
        draft = store.get_active_by_conversation(payload.conversation_id)
        normalized = " ".join(payload.instruction.casefold().split()).rstrip(".!?")
        if draft is not None:
            if normalized in {"está bien", "déjalo así", "guárdalo"}:
                try:
                    adapter, target, relative = _draft_target(
                        request, draft.target_relative_path, draft.content
                    )
                    if target.exists():
                        return _draft_response(
                            draft,
                            "El target ya existe. No se sobrescribió; el borrador sigue activo.",
                            "draft_conflict",
                        )
                    result = adapter.execute(
                        ToolExecutionRequest(
                            "filesystem",
                            "write_text_file",
                            {
                                "relative_path": relative,
                                "content": draft.content,
                                "overwrite_policy": "create_only",
                            },
                        )
                    )
                    data = result.structured_data
                    if not (
                        result.success
                        and result.execution_performed
                        and result.mutation_performed
                        and result.tool_id == "filesystem"
                        and result.operation_id == "write_text_file"
                        and data.get("verification_passed") is True
                        and data.get("created") is True
                        and data.get("relative_path") == relative
                        and data.get("after_digest") == draft.digest
                    ):
                        return _draft_response(
                            draft,
                            "No se pudo verificar la finalización; el borrador sigue activo.",
                            "draft_verification_failed",
                            executed=result.mutation_performed,
                        )
                except (
                    ToolExecutionError,
                    ExecutionForbiddenError,
                    ExecutionValidationError,
                    HTTPException,
                ):
                    return _draft_response(
                        draft,
                        "No se pudo finalizar de forma segura. El target puede haber cambiado; el borrador sigue activo.",
                        "draft_conflict",
                    )
                draft = store.mark_finalized(draft.draft_id, payload.conversation_id)
                return _draft_response(
                    draft,
                    f"Archivo finalizado: {draft.target_relative_path}.",
                    "draft_finalized",
                    executed=True,
                )
            update = re.fullmatch(
                r"\s*(?:cambia|actualiza|modifica) el contenido(?: del borrador)?(?: a)?\s*:\s*(.+)",
                payload.instruction,
                re.I | re.S,
            )
            content = update.group(1) if update else None
            if write is not None and write.relative_path == draft.target_relative_path:
                content = write.content
            if content is not None:
                _draft_target(request, draft.target_relative_path, content)
                draft = store.update(draft.draft_id, payload.conversation_id, content)
                return _draft_response(
                    draft,
                    "Borrador actualizado. El archivo final aún no se ha escrito.",
                )
            return _draft_response(
                draft,
                "Este es el borrador activo. Puedes cambiar el contenido o decir «guárdalo».",
            )
        if write is not None:
            _, target, relative = _draft_target(
                request, write.relative_path, write.content
            )
            if not target.exists():
                draft = store.create(payload.conversation_id, relative, write.content)
                return _draft_response(
                    draft, "Borrador creado. El archivo final aún no se ha escrito."
                )
        return None


@router.post("/conversation/respond", response_model=ConversationResponse)
def respond_to_conversation(
    payload: ConversationRequest,
    request: Request,
) -> ConversationResponse:
    if is_capability_inquiry(payload.instruction):
        return ConversationResponse(
            message=request.app.state.capability_summary_service.response(payload.instruction),
            planning_status="capability_summary",
            plan=None,
            reasoning_invoked=False,
        )
    filesystem_write = requested_workspace_write(payload.instruction)
    filesystem_read = requested_workspace_read(payload.instruction)
    normalized_instruction = " ".join(payload.instruction.casefold().split()).rstrip("?.!,;:")
    filesystem_list = normalized_instruction in {
        "lista los archivos del workspace", "lista archivos del workspace",
        "list workspace files", "list the workspace files",
    }
    try:
        if filesystem_write is not None:
            _reject_draft_storage(filesystem_write.relative_path)
        if filesystem_read is not None:
            _reject_draft_storage(filesystem_read)
            policy = request.app.state.workspace_policy
            if policy is not None:
                _reject_draft_storage(policy.validate_relative(filesystem_read, expect="file"))
        draft_response = _filesystem_draft_conversation(payload, request, filesystem_write)
        if draft_response is not None:
            return draft_response
    except (ToolExecutionError, ExecutionForbiddenError, ExecutionValidationError) as error:
        raise HTTPException(status_code=403, detail=str(error)) from error
    except (FilesystemDraftError, OSError, ValueError, KeyError) as error:
        raise HTTPException(status_code=409, detail="El borrador filesystem no está disponible.") from error
    if filesystem_write is not None:
        context_request = AgentContextRequest(
            instruction=payload.instruction, preferred_agent_id="filesystem",
            include_context=False, allow_execution=False,
        )
        review = request.app.state.agent_plan_review_service.create(context_request)
        return ConversationResponse(
            message="Preparé una revisión para crear el archivo. No se ha escrito nada todavía.",
            planning_status="pending_review", plan=plan_response(review.plan),
            reasoning_invoked=False, review_id=review.review_id,
        )
    if filesystem_read is not None or filesystem_list:
        operation = "read_file" if filesystem_read is not None else "list_directory"
        arguments = (
            {"relative_path": filesystem_read}
            if filesystem_read is not None
            else {"relative_path": "."}
        )
        try:
            adapter = request.app.state.tool_adapter_registry.get("filesystem", operation)
            result = adapter.execute(ToolExecutionRequest("filesystem", operation, arguments))
        except (KeyError, ToolExecutionError) as error:
            detail = getattr(error, "safe_message", "The workspace request could not be completed.")
            raise HTTPException(status_code=403, detail=detail) from error
        if filesystem_list:
            output = "\n".join(
                line for line in result.output.splitlines()
                if line.split("\t")[-1].casefold() != "cauco-drafts"
            )
        else:
            output = result.output
        return ConversationResponse(
            message=output or "No workspace entries were found.", planning_status="executed",
            plan=None, reasoning_invoked=False, execution_performed=True,
        )
    context_request = AgentContextRequest(
        instruction=payload.instruction,
        intent=payload.intent,
        preferred_agent_id=payload.preferred_agent_id,
        include_context=payload.include_context,
        max_context_items=payload.max_context_items,
        max_excerpt_chars=payload.max_excerpt_chars,
        allow_execution=False,
        timezone=payload.timezone,
        calendar_reference=payload.calendar_reference,
        default_event_duration_minutes=payload.default_event_duration_minutes,
        mail_account_reference=payload.mail_account_reference,
        mailbox_reference=payload.mailbox_reference,
    )
    try:
        outcome = request.app.state.reasoning_aware_planning_service.plan(
            context_request, use_reasoning=False
        )
        planning = outcome.planning
        if planning.plan is not None:
            plan = plan_response(planning.plan)
            message = plan.objective
            if plan.steps:
                message += "\n" + "\n".join(
                    f"{index}. {step.description}"
                    for index, step in enumerate(plan.steps, start=1)
                )
            return ConversationResponse(
                message=message,
                planning_status="planned",
                plan=plan,
                reasoning_invoked=False,
            )
        if not payload.use_reasoning:
            fallback = _deterministic_conversation_fallback(payload.instruction)
            if fallback is not None:
                return ConversationResponse(
                    message=fallback,
                    planning_status="no_match",
                    plan=None,
                    reasoning_invoked=False,
                )
            raise HTTPException(status_code=503, detail="No advisory conversation provider is enabled.")
        advisory = request.app.state.reasoning_orchestration_service.advisory_response(
            ReasoningRequest(instruction=payload.instruction, agent_id=payload.preferred_agent_id)
        )
        if advisory.result is None or not advisory.result.text.strip():
            fallback = _ai_conversation_fallback(request, payload.instruction)
            if fallback is not None:
                return ConversationResponse(
                    message=fallback,
                    planning_status="no_match",
                    plan=None,
                    reasoning_invoked=advisory.reasoning_invoked,
                )
            raise HTTPException(status_code=503, detail="Advisory conversation is unavailable; no action was taken.")
        return ConversationResponse(
            message=advisory.result.text.strip(),
            planning_status="no_match",
            plan=None,
            reasoning_invoked=advisory.reasoning_invoked,
        )
    except HTTPException:
        raise
    except UnknownPreferredAgentError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@router.post("/plan", response_model=ReasoningAwarePlanningResponse)
def plan_with_reasoning(
    payload: ReasoningPlanRequest,
    request: Request,
) -> ReasoningAwarePlanningResponse:
    try:
        context_request = AgentContextRequest(
            instruction=payload.instruction,
            intent=payload.intent,
            preferred_agent_id=payload.preferred_agent_id,
            include_context=payload.include_context,
            max_context_items=payload.max_context_items,
            max_excerpt_chars=payload.max_excerpt_chars,
            allow_execution=False,
            timezone=payload.timezone,
            calendar_reference=payload.calendar_reference,
            default_event_duration_minutes=payload.default_event_duration_minutes,
            mail_account_reference=payload.mail_account_reference,
            mailbox_reference=payload.mailbox_reference,
        )
        outcome = request.app.state.reasoning_aware_planning_service.plan(
            context_request,
            use_reasoning=payload.use_reasoning,
        )
        return reasoning_planning_response(outcome)
    except UnknownPreferredAgentError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(error)) from error
    except TypeError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="The selected agent cannot construct a deterministic plan.",
        ) from error
    except HTTPException:
        raise
    except Exception as error:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="The advisory planning request could not be completed.",
        ) from error


def reasoning_planning_response(
    outcome: ReasoningAwarePlanningOutcome,
) -> ReasoningAwarePlanningResponse:
    planning = outcome.planning
    routed = planning.routing
    selected = None
    if routed.selected_agent_id is not None and routed.selected_agent_name is not None:
        selected = SelectedAgentResponse(
            id=routed.selected_agent_id,
            name=routed.selected_agent_name,
        )
    return ReasoningAwarePlanningResponse(
        reasoning_requested=outcome.reasoning_requested,
        reasoning_invoked=outcome.reasoning_invoked,
        proposal_produced=outcome.proposal_produced,
        proposal_validated=outcome.proposal_validated,
        planning_context_enriched=outcome.planning_context_enriched,
        provider=outcome.provider,
        model=outcome.model,
        explanation=outcome.explanation,
        planning=ReasoningPlanningDataResponse(
            status="planned" if planning.plan is not None else "no_match",
            routing=ReasoningPlanningRoutingResponse(
                selected_agent=selected,
                match=match_response(routed.match) if routed.match is not None else None,
                matches=[match_response(match) for match in routed.matches],
                preferred_agent_rejected=routed.preferred_agent_rejected,
            ),
            context=context_response(planning.context) if planning.context is not None else None,
            plan=plan_response(planning.plan) if planning.plan is not None else None,
        ),
    )
