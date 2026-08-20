from dataclasses import dataclass

from cauco_agents.models import (
    AgentPlanStep,
    AgentToolReference,
    CalendarCreateEventInput,
    CalendarListEventsInput,
)
from cauco_agents.skills.models import SkillCompilation, SkillDefinition


@dataclass(frozen=True, slots=True)
class CalendarInspectScheduleInput:
    list_input: CalendarListEventsInput | None
    open_questions: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "open_questions", tuple(self.open_questions))


@dataclass(frozen=True, slots=True)
class CalendarPrepareEventInput:
    list_input: CalendarListEventsInput | None
    create_input: CalendarCreateEventInput | None
    open_questions: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "open_questions", tuple(self.open_questions))


class CalendarInspectScheduleSkill:
    definition = SkillDefinition(
        skill_id="calendar.inspect_schedule",
        version=1,
        description="Compile a bounded calendar event-range inspection plan.",
        supported_agent_ids=("calendar",),
    )

    def compile(self, input_data: CalendarInspectScheduleInput) -> SkillCompilation:
        steps = ()
        if input_data.list_input is not None:
            steps = (
                AgentPlanStep(
                    1,
                    "Inspect the approved calendar range",
                    "Read bounded event metadata for the exact approved time range.",
                    (),
                    "List events without modifying Calendar.",
                    False,
                    False,
                    tool_reference=AgentToolReference("calendar", "list_events"),
                    operation_input=input_data.list_input,
                ),
            )
        return SkillCompilation(
            self.definition.skill_id,
            self.definition.version,
            steps,
            open_questions=input_data.open_questions,
        )


class CalendarPrepareEventSkill:
    definition = SkillDefinition(
        skill_id="calendar.prepare_event",
        version=1,
        description="Compile bounded calendar inspection and preview-first event creation steps.",
        supported_agent_ids=("calendar",),
    )

    def compile(self, input_data: CalendarPrepareEventInput) -> SkillCompilation:
        steps: list[AgentPlanStep] = []
        if input_data.list_input is not None:
            steps.append(
                AgentPlanStep(
                    len(steps) + 1,
                    "Inspect the proposed event range",
                    "Read bounded event metadata before proposing a calendar mutation.",
                    (),
                    "Check the exact approved range for existing events.",
                    False,
                    False,
                    tool_reference=AgentToolReference("calendar", "list_events"),
                    operation_input=input_data.list_input,
                )
            )
        if input_data.create_input is not None:
            steps.append(
                AgentPlanStep(
                    len(steps) + 1,
                    "Prepare calendar event creation",
                    "Create only the exact typed event after preview and confirmation.",
                    (),
                    "Create the approved Calendar event through the mutation boundary.",
                    True,
                    False,
                    ("Event creation requires a separate single-use confirmation.",),
                    AgentToolReference("calendar", "create_event"),
                    input_data.create_input,
                )
            )
        return SkillCompilation(
            self.definition.skill_id,
            self.definition.version,
            tuple(steps),
            open_questions=input_data.open_questions,
        )
