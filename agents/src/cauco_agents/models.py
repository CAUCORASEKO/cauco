import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import PurePosixPath
from types import MappingProxyType
from typing import Any, Literal, Mapping, TypeAlias

from cauco_tools import GitAddInput, GitCommitInput, GitPushInput

AgentContextValue: TypeAlias = str | int | float | bool | None
DEFAULT_MAX_CONTEXT_ITEMS = 4
DEFAULT_MAX_EXCERPT_CHARS = 2000
MAX_CONTEXT_ITEMS = 8
MIN_EXCERPT_CHARS = 100
MAX_EXCERPT_CHARS = 4000
MAX_TOTAL_CONTEXT_CHARS = 7000
STEP_OUTPUT_BINDING_MARKER = "$step_output"


@dataclass(frozen=True, slots=True)
class StepOutputBinding:
    source_step_index: int
    path: tuple[str | int, ...]
    value_type: Literal["string", "integer", "number", "boolean"] = "string"

    def __post_init__(self) -> None:
        if (
            not isinstance(self.source_step_index, int)
            or isinstance(self.source_step_index, bool)
            or self.source_step_index < 1
        ):
            raise ValueError("Binding source step index must be positive.")
        path = tuple(self.path)
        if not path or len(path) > 16:
            raise ValueError("Binding paths must contain between 1 and 16 segments.")
        for segment in path:
            if isinstance(segment, str):
                if not segment or len(segment) > 100:
                    raise ValueError(
                        "Binding mapping keys must be bounded and non-empty."
                    )
            elif (
                not isinstance(segment, int)
                or isinstance(segment, bool)
                or not 0 <= segment <= 999
            ):
                raise ValueError("Binding list indexes must be between 0 and 999.")
        if len("/".join(str(segment) for segment in path)) > 500:
            raise ValueError("Binding path description cannot exceed 500 characters.")
        if self.value_type not in {"string", "integer", "number", "boolean"}:
            raise ValueError("Binding value type is unsupported.")
        object.__setattr__(self, "path", path)

    @property
    def path_description(self) -> str:
        return "/".join(str(segment) for segment in self.path)


def encode_step_output_bindings(value: Any) -> Any:
    if isinstance(value, StepOutputBinding):
        return {
            STEP_OUTPUT_BINDING_MARKER: {
                "source_step_index": value.source_step_index,
                "path": list(value.path),
                "value_type": value.value_type,
            }
        }
    if isinstance(value, Mapping):
        return {
            str(key): encode_step_output_bindings(item) for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [encode_step_output_bindings(item) for item in value]
    return value


def decode_step_output_bindings(value: Any) -> Any:
    if isinstance(value, dict):
        if set(value) == {STEP_OUTPUT_BINDING_MARKER}:
            payload = value[STEP_OUTPUT_BINDING_MARKER]
            if not isinstance(payload, dict) or set(payload) != {
                "source_step_index",
                "path",
                "value_type",
            }:
                raise ValueError("Stored step output binding is invalid.")
            path = payload["path"]
            if not isinstance(path, list):
                raise ValueError("Stored step output binding path is invalid.")
            return StepOutputBinding(
                source_step_index=payload["source_step_index"],
                path=tuple(path),
                value_type=payload["value_type"],
            )
        return {
            str(key): decode_step_output_bindings(item) for key, item in value.items()
        }
    if isinstance(value, list):
        return tuple(decode_step_output_bindings(item) for item in value)
    return value


def contains_step_output_binding(value: Any) -> bool:
    if isinstance(value, StepOutputBinding):
        return True
    if isinstance(value, Mapping):
        return any(contains_step_output_binding(item) for item in value.values())
    if isinstance(value, (list, tuple)):
        return any(contains_step_output_binding(item) for item in value)
    fields = getattr(value, "__dataclass_fields__", {})
    return any(contains_step_output_binding(getattr(value, name)) for name in fields)


def normalize_whitespace(value: str) -> str:
    return " ".join(value.split())


@dataclass(frozen=True, slots=True)
class AgentRequest:
    instruction: str
    intent: str | None = None
    context: Mapping[str, AgentContextValue] = field(default_factory=dict)
    preferred_agent_id: str | None = None
    allow_execution: bool = False

    def __post_init__(self) -> None:
        instruction = normalize_whitespace(self.instruction)
        if not instruction:
            raise ValueError("Agent instruction cannot be empty.")
        if len(instruction) > 4000:
            raise ValueError("Agent instruction cannot exceed 4000 characters.")
        object.__setattr__(self, "instruction", instruction)

        intent = normalize_whitespace(self.intent) if self.intent is not None else None
        preferred = (
            normalize_whitespace(self.preferred_agent_id)
            if self.preferred_agent_id is not None
            else None
        )
        object.__setattr__(self, "intent", intent or None)
        object.__setattr__(self, "preferred_agent_id", preferred or None)

        if len(self.context) > 20:
            raise ValueError("Agent context cannot contain more than 20 entries.")
        copied_context: dict[str, AgentContextValue] = {}
        for key, value in self.context.items():
            normalized_key = normalize_whitespace(key)
            if not normalized_key or len(normalized_key) > 100:
                raise ValueError("Agent context keys must contain 1 to 100 characters.")
            if not isinstance(value, (str, int, float, bool, type(None))):
                raise ValueError("Agent context values must be JSON scalar values.")
            if isinstance(value, str) and len(value) > 1000:
                raise ValueError(
                    "Agent context text values cannot exceed 1000 characters."
                )
            copied_context[normalized_key] = value
        object.__setattr__(self, "context", MappingProxyType(copied_context))


@dataclass(frozen=True, slots=True)
class AgentMatch:
    agent_id: str
    matched: bool
    score: int
    matched_signals: tuple[str, ...]
    reasoning: tuple[str, ...]
    priority: int

    def __post_init__(self) -> None:
        if not 0 <= self.score <= 100:
            raise ValueError("Agent match score must be between 0 and 100.")
        if self.matched != (self.score > 0):
            raise ValueError("Agent match state must agree with its score.")


@dataclass(frozen=True, slots=True)
class AgentResult:
    agent_id: str
    agent_name: str
    status: str
    summary: str
    proposed_actions: tuple[str, ...]
    warnings: tuple[str, ...]
    requires_confirmation: bool
    execution_performed: bool = False
    metadata: Mapping[str, AgentContextValue] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.execution_performed:
            raise ValueError("Phase 5A agents cannot report performed execution.")
        object.__setattr__(self, "metadata", MappingProxyType(dict(self.metadata)))


@dataclass(frozen=True, slots=True)
class AgentRouteResult:
    request: AgentRequest
    selected_agent_id: str | None
    selected_agent_name: str | None
    match: AgentMatch | None
    matches: tuple[AgentMatch, ...]
    result: AgentResult | None
    preferred_agent_rejected: bool = False


@dataclass(frozen=True, slots=True)
class AgentContextRequest:
    instruction: str
    intent: str | None = None
    preferred_agent_id: str | None = None
    include_context: bool = True
    max_context_items: int = DEFAULT_MAX_CONTEXT_ITEMS
    max_excerpt_chars: int = DEFAULT_MAX_EXCERPT_CHARS
    allow_execution: bool = False
    timezone: str | None = None
    calendar_reference: str | None = None
    default_event_duration_minutes: int | None = None
    mail_account_reference: str | None = None
    mailbox_reference: str | None = None

    def __post_init__(self) -> None:
        normalized = AgentRequest(
            instruction=self.instruction,
            intent=self.intent,
            preferred_agent_id=self.preferred_agent_id,
            allow_execution=self.allow_execution,
        )
        object.__setattr__(self, "instruction", normalized.instruction)
        object.__setattr__(self, "intent", normalized.intent)
        object.__setattr__(self, "preferred_agent_id", normalized.preferred_agent_id)
        if self.timezone is not None and (
            not self.timezone.strip()
            or len(self.timezone) > 100
            or "\x00" in self.timezone
        ):
            raise ValueError("Planning timezone is invalid.")
        if self.calendar_reference is not None:
            _calendar_reference(self.calendar_reference)
        if (
            self.mail_account_reference is not None
            and re.fullmatch(
                r"mailacct_[A-Za-z0-9_-]{8,80}", self.mail_account_reference
            )
            is None
        ):
            raise ValueError("Email account reference is invalid.")
        if (
            self.mailbox_reference is not None
            and re.fullmatch(r"mailbox_[A-Za-z0-9_-]{8,80}", self.mailbox_reference)
            is None
        ):
            raise ValueError("Email mailbox reference is invalid.")
        if self.default_event_duration_minutes is not None and (
            isinstance(self.default_event_duration_minutes, bool)
            or not 1 <= self.default_event_duration_minutes <= 1440
        ):
            raise ValueError(
                "Default event duration must be between 1 and 1440 minutes."
            )
        if not 1 <= self.max_context_items <= MAX_CONTEXT_ITEMS:
            raise ValueError(
                f"max_context_items must be between 1 and {MAX_CONTEXT_ITEMS}."
            )
        if not MIN_EXCERPT_CHARS <= self.max_excerpt_chars <= MAX_EXCERPT_CHARS:
            raise ValueError(
                "max_excerpt_chars must be between "
                f"{MIN_EXCERPT_CHARS} and {MAX_EXCERPT_CHARS}."
            )

    def routing_request(self) -> AgentRequest:
        return AgentRequest(
            instruction=self.instruction,
            intent=self.intent,
            preferred_agent_id=self.preferred_agent_id,
            allow_execution=self.allow_execution,
        )


@dataclass(frozen=True, slots=True)
class AgentMemoryReference:
    memory_id: str
    name: str
    kind: str
    layer: str
    title: str
    relative_path: str
    reason_selected: str
    excerpt: str
    excerpt_truncated: bool
    modified_at: str | None = None
    excerpt_strategy: str = "document_start"
    selected_headings: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class AgentContext:
    agent_id: str
    instruction: str
    resolved_intent: str | None
    memory_references: tuple[AgentMemoryReference, ...]
    context_summary: str
    limitations: tuple[str, ...]
    metadata: Mapping[str, AgentContextValue] = field(default_factory=dict)
    learning_guidance: tuple[Mapping[str, object], ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "metadata", MappingProxyType(dict(self.metadata)))
        object.__setattr__(
            self,
            "learning_guidance",
            tuple(MappingProxyType(dict(item)) for item in self.learning_guidance),
        )


@dataclass(frozen=True, slots=True)
class AgentToolReference:
    tool_id: str
    operation_id: str
    target: str | None = None

    def __post_init__(self) -> None:
        pattern = r"[a-z][a-z0-9]*(?:_[a-z0-9]+)*"
        if not re.fullmatch(pattern, self.tool_id) or not re.fullmatch(
            pattern, self.operation_id
        ):
            raise ValueError(
                "Agent tool and operation IDs must use lowercase snake_case."
            )
        target = self.target.strip() if self.target is not None else None
        if target is not None and (not target or len(target) > 500 or "\x00" in target):
            raise ValueError(
                "Agent tool targets must contain 1 to 500 safe characters."
            )
        if target is not None and (
            target.startswith(("/", "\\")) or re.match(r"^[A-Za-z]:", target)
        ):
            raise ValueError("Agent tool targets cannot be absolute paths.")
        if (
            target is not None
            and ".." in PurePosixPath(target.replace("\\", "/")).parts
        ):
            raise ValueError("Agent tool targets cannot traverse parent directories.")
        object.__setattr__(self, "target", target)


@dataclass(frozen=True, slots=True)
class MemoryCreateProposalInput:
    proposal_type: Literal[
        "add_task", "add_decision", "add_relationship_note", "add_project_note"
    ]
    content: str

    def __post_init__(self) -> None:
        content = normalize_whitespace(self.content)
        if not content or len(content) > 4000:
            raise ValueError(
                "Memory proposal content must contain 1 to 4000 characters."
            )
        object.__setattr__(self, "content", content)


@dataclass(frozen=True, slots=True)
class MemoryConfirmProposalInput:
    proposal_id: str

    def __post_init__(self) -> None:
        if not re.fullmatch(r"proposal_[0-9a-f]{24}", self.proposal_id):
            raise ValueError("Memory confirmation requires an exact proposal ID.")


@dataclass(frozen=True, slots=True)
class FilesystemWriteTextInput:
    relative_path: str
    content: str
    overwrite_policy: Literal["create_only", "replace_existing"]

    def __post_init__(self) -> None:
        reference = AgentToolReference(
            "filesystem", "write_text_file", self.relative_path
        )
        if len(self.content) > 100_000 or "\x00" in self.content:
            raise ValueError(
                "Filesystem text content must be UTF-8 text up to 100000 characters."
            )
        object.__setattr__(self, "relative_path", reference.target)


def _calendar_datetime(value: str, field_name: str) -> datetime:
    if not isinstance(value, str) or len(value) > 100:
        raise ValueError(f"Calendar {field_name} must be a bounded ISO-8601 timestamp.")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError(
            f"Calendar {field_name} must be a valid ISO-8601 timestamp."
        ) from error
    if parsed.tzinfo is None:
        raise ValueError(f"Calendar {field_name} must include a timezone offset.")
    return parsed


def _calendar_reference(value: str | None) -> str | None:
    if value is not None and not re.fullmatch(r"calendar_[A-Za-z0-9_-]{8,80}", value):
        raise ValueError("Calendar reference is invalid.")
    return value


@dataclass(frozen=True, slots=True)
class EmailListAccountsInput:
    pass


@dataclass(frozen=True, slots=True)
class EmailListMailboxesInput:
    account_reference: str | StepOutputBinding

    def __post_init__(self) -> None:
        if isinstance(self.account_reference, StepOutputBinding):
            if self.account_reference.value_type != "string":
                raise ValueError(
                    "Email account reference binding must resolve to a string."
                )
            return
        if not isinstance(self.account_reference, str) or not re.fullmatch(
            r"mailacct_[A-Za-z0-9_-]{8,80}", self.account_reference
        ):
            raise ValueError("Email account reference is invalid.")


@dataclass(frozen=True, slots=True)
class EmailListMessagesInput:
    mailbox_reference: str | StepOutputBinding
    limit: int = 20

    def __post_init__(self) -> None:
        if isinstance(self.mailbox_reference, StepOutputBinding):
            if self.mailbox_reference.value_type != "string":
                raise ValueError(
                    "Email mailbox reference binding must resolve to a string."
                )
        elif not isinstance(self.mailbox_reference, str) or not re.fullmatch(
            r"mailbox_[A-Za-z0-9_-]{8,80}", self.mailbox_reference
        ):
            raise ValueError("Email mailbox reference is invalid.")
        if (
            not isinstance(self.limit, int)
            or isinstance(self.limit, bool)
            or not 1 <= self.limit <= 20
        ):
            raise ValueError("Email message list limit must be between 1 and 20.")


@dataclass(frozen=True, slots=True)
class EmailDraftInput:
    recipient: str
    subject: str
    body: str

    def __post_init__(self) -> None:
        recipient = self.recipient.strip()
        subject = " ".join(self.subject.split())

        if (
            not recipient
            or len(recipient) > 254
            or recipient.count("@") != 1
            or any(character.isspace() for character in recipient)
        ):
            raise ValueError("Email recipient must be a valid bounded address.")

        local_part, domain = recipient.split("@", 1)
        if not local_part or not domain or "." not in domain:
            raise ValueError("Email recipient must be a valid bounded address.")

        if not subject or len(subject) > 300 or "\x00" in subject:
            raise ValueError("Email subject must contain 1 to 300 safe characters.")

        if (
            not isinstance(self.body, str)
            or len(self.body) > 4_000
            or "\x00" in self.body
        ):
            raise ValueError("Email body must contain at most 4000 safe characters.")

        object.__setattr__(self, "recipient", recipient)
        object.__setattr__(self, "subject", subject)


@dataclass(frozen=True, slots=True)
class CalendarListEventsInput:
    start: str
    end: str
    limit: int = 100
    calendar_reference: str | None = None

    def __post_init__(self) -> None:
        starts = _calendar_datetime(self.start, "start")
        ends = _calendar_datetime(self.end, "end")
        if starts >= ends or ends - starts > timedelta(days=31):
            raise ValueError(
                "Calendar event range must be positive and at most 31 days."
            )
        if isinstance(self.limit, bool) or not 1 <= self.limit <= 100:
            raise ValueError("Calendar event range limit must be between 1 and 100.")
        object.__setattr__(
            self, "calendar_reference", _calendar_reference(self.calendar_reference)
        )


@dataclass(frozen=True, slots=True)
class CalendarCreateEventInput:
    title: str
    start: str
    end: str
    all_day: bool
    calendar_reference: str | None = None
    location: str | None = None
    notes: str | None = None

    def __post_init__(self) -> None:
        title = normalize_whitespace(self.title)
        if (
            not title
            or len(title) > 300
            or any(ord(character) < 32 for character in title)
        ):
            raise ValueError(
                "Calendar event title must contain 1 to 300 safe characters."
            )
        starts = _calendar_datetime(self.start, "start")
        ends = _calendar_datetime(self.end, "end")
        if starts >= ends or ends - starts > timedelta(days=31):
            raise ValueError(
                "Calendar event duration must be positive and at most 31 days."
            )
        if not isinstance(self.all_day, bool):
            raise ValueError("Calendar all-day flag must be boolean.")
        for field_name, value, maximum in (
            ("location", self.location, 300),
            ("notes", self.notes, 1000),
        ):
            if value is not None and (
                len(value) > maximum
                or "\x00" in value
                or any(ord(character) < 9 for character in value)
            ):
                raise ValueError(f"Calendar event {field_name} is invalid.")
        object.__setattr__(self, "title", title)
        object.__setattr__(
            self, "calendar_reference", _calendar_reference(self.calendar_reference)
        )


AgentOperationInput: TypeAlias = (
    MemoryCreateProposalInput
    | MemoryConfirmProposalInput
    | FilesystemWriteTextInput
    | GitAddInput
    | GitCommitInput
    | GitPushInput
    | CalendarListEventsInput
    | CalendarCreateEventInput
    | EmailListAccountsInput
    | EmailListMailboxesInput
    | EmailListMessagesInput
    | EmailDraftInput
)


@dataclass(frozen=True, slots=True)
class AgentPlanStep:
    order: int
    title: str
    description: str
    source_memory_ids: tuple[str, ...]
    proposed_action: str
    requires_confirmation: bool
    execution_available: bool
    warnings: tuple[str, ...] = ()
    tool_reference: AgentToolReference | None = None
    operation_input: AgentOperationInput | None = None

    def __post_init__(self) -> None:
        if self.order < 1:
            raise ValueError("Agent plan step order must be positive.")
        if self.execution_available:
            raise ValueError("Phase 5B plan execution cannot be available.")
        if self.tool_reference is None:
            raise ValueError("Phase 6A plan steps must reference a tool operation.")
        # Input shape belongs to the registered operation/adapter contract, not
        # to the shared plan model.  Readiness performs that validation without
        # making plan construction aware of individual tools.


@dataclass(frozen=True, slots=True)
class AgentPlan:
    agent_id: str
    agent_name: str
    status: str
    objective: str
    context_used: bool
    steps: tuple[AgentPlanStep, ...]
    open_questions: tuple[str, ...]
    warnings: tuple[str, ...]
    requires_confirmation: bool
    execution_performed: bool = False
    metadata: Mapping[str, AgentContextValue] = field(default_factory=dict)
    plan_version: int = 1

    def __post_init__(self) -> None:
        if self.execution_performed:
            raise ValueError("Phase 5B agents cannot report performed execution.")
        if self.plan_version != 1:
            raise ValueError("Only ExecutionPlan version 1 is supported.")
        expected_orders = tuple(range(1, len(self.steps) + 1))
        if tuple(step.order for step in self.steps) != expected_orders:
            raise ValueError("Agent plan steps must use contiguous one-based ordering.")
        object.__setattr__(self, "metadata", MappingProxyType(dict(self.metadata)))
