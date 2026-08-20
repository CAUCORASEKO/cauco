import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta, timezone, tzinfo
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from cauco_agents.base import AgentMetadata
from cauco_agents.builtin.base import DeterministicSignalAgent
from cauco_agents.models import (
    AgentContext,
    AgentPlan,
    CalendarCreateEventInput,
    CalendarListEventsInput,
)
from cauco_agents.skills import (
    CalendarInspectScheduleInput,
    CalendarPrepareEventInput,
    SkillRegistry,
    create_default_skill_registry,
)


class CalendarAgent(DeterministicSignalAgent):
    metadata = AgentMetadata(
        agent_id="calendar",
        name="Calendar Agent",
        description="Recognizes bounded calendar inspection and event creation requests.",
        version="1.0.0",
        capabilities=("calendar_inspection_proposal", "calendar_event_proposal"),
        supported_intents=("calendar",),
        priority=25,
    )
    signals = (
        "calendar",
        "calendars",
        "calendario",
        "calendarios",
        "event",
        "events",
        "evento",
        "eventos",
        "appointment",
        "appointments",
        "cita",
        "citas",
        "schedule",
        "agenda",
        "agendas",
    )

    def __init__(
        self,
        skill_registry: SkillRegistry | None = None,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.skill_registry = skill_registry or create_default_skill_registry()
        self.clock = clock or (lambda: datetime.now(tz=UTC))

    def summary(self) -> str:
        return "This request belongs to Calendar planning, but no calendar data was accessed."

    def proposed_actions(self) -> tuple[str, ...]:
        return (
            "Resolve the exact calendar range and timezone.",
            "Inspect bounded event metadata when the range is complete.",
            "Prepare event creation only from complete typed details.",
        )

    def requires_confirmation(self) -> bool:
        return True

    def plan(
        self, context: AgentContext, *, allow_execution: bool = False
    ) -> AgentPlan:
        creation = is_creation_request(context.instruction)
        resolved = resolve_calendar_request(context, self.clock())
        if creation:
            compilation = self.skill_registry.get("calendar.prepare_event").compile(
                CalendarPrepareEventInput(
                    list_input=resolved.list_input,
                    create_input=resolved.create_input,
                    open_questions=resolved.open_questions,
                )
            )
        else:
            compilation = self.skill_registry.get("calendar.inspect_schedule").compile(
                CalendarInspectScheduleInput(
                    list_input=resolved.list_input,
                    open_questions=resolved.open_questions,
                )
            )
        warnings = [
            "No Calendar data was read and no event was created during planning.",
            "Relative dates are resolved only against the snapshotted planning timezone.",
        ]
        warnings.extend(compilation.warnings)
        if allow_execution:
            warnings.append(
                "allow_execution was ignored; execution requires review, approval, and runtime."
            )
        return AgentPlan(
            agent_id=self.id,
            agent_name=self.metadata.name,
            status="proposal_only",
            objective=f"Prepare a safe Calendar workflow for: {context.instruction}",
            context_used=bool(context.memory_references),
            steps=compilation.steps,
            open_questions=compilation.open_questions,
            warnings=tuple(warnings),
            requires_confirmation=creation,
            metadata={
                "framework_phase": "calendar_skill_v1",
                "skill_id": compilation.skill_id,
                "temporal_input_complete": not compilation.open_questions,
            },
        )


@dataclass(frozen=True, slots=True)
class ResolvedCalendarRequest:
    list_input: CalendarListEventsInput | None
    create_input: CalendarCreateEventInput | None
    open_questions: tuple[str, ...]


def is_creation_request(instruction: str) -> bool:
    normalized = instruction.casefold()
    return bool(
        re.search(
            r"\b(create|add|schedule|crea|crear|agrega|agregar|programa|programar)\b",
            normalized,
        )
    )


def resolve_calendar_request(
    context: AgentContext, reference_time: datetime
) -> ResolvedCalendarRequest:
    instruction = context.instruction
    creation = is_creation_request(instruction)
    questions: list[str] = []
    timezone_value = _string_metadata(context, "timezone") or _timezone_in_instruction(
        instruction
    )
    zone = _timezone(timezone_value)
    if zone is None:
        questions.append("Which timezone should be used for this Calendar request?")
    calendar_reference = _string_metadata(
        context, "calendar_reference"
    ) or _calendar_in_instruction(instruction)
    requested_date = _date_in_instruction(instruction, reference_time, zone)
    if requested_date is None:
        if _iso_date_in_instruction(instruction):
            questions.append("What valid exact date should be used?")
        elif not _has_relative_date_expression(instruction):
            questions.append("What exact date should be used?")
    requested_time = _time_in_instruction(instruction)
    if creation and requested_time is None:
        questions.append("What exact start time should be used?")

    list_input: CalendarListEventsInput | None = None
    create_input: CalendarCreateEventInput | None = None
    if not creation and zone is not None and requested_date is not None:
        starts = datetime.combine(requested_date, time.min, zone)
        ends = starts + timedelta(days=1)
        list_input = CalendarListEventsInput(
            starts.isoformat(), ends.isoformat(), 100, calendar_reference
        )
    if creation:
        duration = _duration_minutes(instruction, context)
        if duration is None:
            questions.append("How long should the event last?")
        title = _event_title(instruction)
        if title is None:
            questions.append("What exact title should the event have?")
        if (
            zone is not None
            and requested_date is not None
            and requested_time is not None
            and duration is not None
        ):
            starts = datetime.combine(requested_date, requested_time, zone)
            ends = starts + timedelta(minutes=duration)
            list_input = CalendarListEventsInput(
                starts.isoformat(), ends.isoformat(), 100, calendar_reference
            )
            if title is not None:
                create_input = CalendarCreateEventInput(
                    title,
                    starts.isoformat(),
                    ends.isoformat(),
                    False,
                    calendar_reference,
                )
    return ResolvedCalendarRequest(list_input, create_input, tuple(questions))


def _string_metadata(context: AgentContext, key: str) -> str | None:
    value = context.metadata.get(key)
    return value if isinstance(value, str) and value else None


def _timezone(value: str | None) -> tzinfo | None:
    if value is None:
        return None
    offset = re.fullmatch(r"(?:UTC)?([+-])(\d{2}):(\d{2})", value, flags=re.IGNORECASE)
    if offset is not None:
        hours, minutes = int(offset.group(2)), int(offset.group(3))
        if hours > 14 or minutes > 59 or (hours == 14 and minutes != 0):
            return None
        delta = timedelta(hours=hours, minutes=minutes)
        return timezone(delta if offset.group(1) == "+" else -delta)
    try:
        return ZoneInfo(value)
    except (ZoneInfoNotFoundError, ValueError):
        return None


def _timezone_in_instruction(instruction: str) -> str | None:
    offset = re.search(r"\bUTC[+-]\d{2}:\d{2}\b", instruction, flags=re.IGNORECASE)
    if offset is not None:
        return offset.group(0).upper()
    zone = re.search(r"\b[A-Z][A-Za-z_]+/[A-Z][A-Za-z_]+\b", instruction)
    return zone.group(0) if zone is not None else None


def _date_in_instruction(
    instruction: str, reference_time: datetime, zone: tzinfo | None
) -> date | None:
    match = re.search(r"\b(\d{4}-\d{2}-\d{2})\b", instruction)
    if match is not None:
        try:
            return date.fromisoformat(match.group(1))
        except ValueError:
            return None
    normalized = instruction.casefold()
    if zone is None:
        return None
    local_date = reference_time.astimezone(zone).date()
    if "mañana" in normalized or "tomorrow" in normalized:
        return local_date + timedelta(days=1)
    if re.search(r"\b(hoy|today)\b", normalized):
        return local_date
    return None


def _iso_date_in_instruction(instruction: str) -> bool:
    return bool(re.search(r"\b\d{4}-\d{2}-\d{2}\b", instruction))


def _has_relative_date_expression(instruction: str) -> bool:
    normalized = instruction.casefold()
    return bool(
        re.search(r"\b(?:mañana|tomorrow)\b", normalized)
        or re.search(r"\b(hoy|today)\b", normalized)
    )


def _time_in_instruction(instruction: str) -> time | None:
    match = re.search(
        r"(?:\ba\s+las\b|\bat\b)\s*(\d{1,2})(?::(\d{2}))?",
        instruction,
        flags=re.IGNORECASE,
    )
    if match is None:
        return None
    hour, minute = int(match.group(1)), int(match.group(2) or 0)
    try:
        return time(hour, minute)
    except ValueError:
        return None


def _duration_minutes(instruction: str, context: AgentContext) -> int | None:
    match = re.search(
        r"(?:durante|por|for)\s+(\d{1,4})\s*(minutos?|minutes?|horas?|hours?)",
        instruction,
        flags=re.IGNORECASE,
    )
    if match is not None:
        value = int(match.group(1))
        if match.group(2).casefold().startswith(("hora", "hour")):
            value *= 60
        return value if 1 <= value <= 1440 else None
    default = context.metadata.get("default_event_duration_minutes")
    return (
        default if isinstance(default, int) and not isinstance(default, bool) else None
    )


def _event_title(instruction: str) -> str | None:
    quoted = re.search(r'["“]([^"”\r\n]{1,300})["”]', instruction)
    if quoted is not None:
        normalized = " ".join(quoted.group(1).split())
        return normalized or None
    named = re.search(
        r"\b(?:evento|event|cita)\s+(?:llamado|called|titulado|titled)\s+(.+?)"
        r"(?=\s+(?:mañana|tomorrow|hoy|today|el\s+\d{4}-\d{2}-\d{2})\b|$)",
        instruction,
        flags=re.IGNORECASE,
    )
    if named is None:
        return None
    normalized = " ".join(named.group(1).split())
    return normalized or None


def _calendar_in_instruction(instruction: str) -> str | None:
    match = re.search(r"\bcalendar_[A-Za-z0-9_-]{8,80}\b", instruction)
    return match.group(0) if match is not None else None
