import subprocess
from datetime import UTC, datetime

import pytest

from cauco_agents import (
    AgentContext,
    CalendarAgent,
    CalendarCreateEventInput,
    CalendarListEventsInput,
    CalendarPrepareEventInput,
    CalendarPrepareEventSkill,
)


REFERENCE_TIME = datetime(2026, 8, 20, 8, 0, tzinfo=UTC)
CALENDAR_REFERENCE = "calendar_abcdefgh"


def context(instruction: str, **metadata) -> AgentContext:
    return AgentContext(
        agent_id="calendar",
        instruction=instruction,
        resolved_intent="calendar",
        memory_references=(),
        context_summary="Calendar planning context.",
        limitations=("No calendar data was accessed.",),
        metadata=metadata,
    )


def test_ambiguous_relative_creation_remains_non_mutating_with_questions() -> None:
    plan = CalendarAgent(clock=lambda: REFERENCE_TIME).plan(
        context("Crea un evento mañana a las 10")
    )

    assert plan.steps == ()
    assert any("timezone" in question for question in plan.open_questions)
    assert any("long" in question for question in plan.open_questions)
    assert any("title" in question for question in plan.open_questions)
    assert not any("calendar_reference" in question for question in plan.open_questions)
    assert not any("exact date" in question for question in plan.open_questions)
    assert plan.execution_performed is False


def test_resolved_relative_creation_compiles_typed_inspection_and_mutation() -> None:
    agent = CalendarAgent(clock=lambda: REFERENCE_TIME)
    planning_context = context(
        'Crea un evento "Planificación" mañana a las 10 durante 60 minutos',
        timezone="Europe/Helsinki",
        calendar_reference=CALENDAR_REFERENCE,
    )

    first = agent.plan(planning_context)
    second = agent.plan(planning_context)

    assert first == second
    assert first.open_questions == ()
    assert [step.tool_reference.operation_id for step in first.steps] == [
        "list_events",
        "create_event",
    ]
    assert isinstance(first.steps[0].operation_input, CalendarListEventsInput)
    creation = first.steps[1].operation_input
    assert isinstance(creation, CalendarCreateEventInput)
    assert creation.title == "Planificación"
    assert creation.start == "2026-08-21T10:00:00+03:00"
    assert creation.end == "2026-08-21T11:00:00+03:00"
    assert creation.calendar_reference == CALENDAR_REFERENCE
    assert first.steps[1].requires_confirmation is True


def test_schedule_inspection_uses_exact_local_day_range() -> None:
    plan = CalendarAgent(clock=lambda: REFERENCE_TIME).plan(
        context(
            "¿Qué eventos tengo mañana en el calendario?", timezone="Europe/Helsinki"
        )
    )

    assert len(plan.steps) == 1
    value = plan.steps[0].operation_input
    assert isinstance(value, CalendarListEventsInput)
    assert value.start == "2026-08-21T00:00:00+03:00"
    assert value.end == "2026-08-22T00:00:00+03:00"


@pytest.mark.parametrize(
    "instruction",
    [
        'Crea un evento "   " el 2026-08-21 a las 10 durante 60 minutos',
        'Crea un evento "Planning" el 2026-02-30 a las 10 durante 60 minutos',
    ],
)
def test_invalid_explicit_calendar_details_remain_open_questions(
    instruction: str,
) -> None:
    plan = CalendarAgent(clock=lambda: REFERENCE_TIME).plan(
        context(
            instruction,
            timezone="Europe/Helsinki",
            calendar_reference=CALENDAR_REFERENCE,
        )
    )

    assert not any(
        step.tool_reference.operation_id == "create_event" for step in plan.steps
    )
    assert plan.open_questions


def test_invalid_utc_offset_does_not_produce_temporal_steps() -> None:
    plan = CalendarAgent(clock=lambda: REFERENCE_TIME).plan(
        context(
            'Crea un evento "Planning" mañana a las 10 durante 60 minutos',
            timezone="UTC+14:30",
            calendar_reference=CALENDAR_REFERENCE,
        )
    )

    assert plan.steps == ()
    assert any("timezone" in question for question in plan.open_questions)


def test_calendar_skill_compilation_performs_no_execution(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def unexpected(*args: object, **kwargs: object) -> None:
        raise AssertionError("Calendar skill attempted execution.")

    monkeypatch.setattr(subprocess, "run", unexpected)
    create = CalendarCreateEventInput(
        "Planning",
        "2026-08-21T10:00:00+03:00",
        "2026-08-21T11:00:00+03:00",
        False,
        CALENDAR_REFERENCE,
    )
    list_input = CalendarListEventsInput(
        create.start, create.end, 100, CALENDAR_REFERENCE
    )
    skill = CalendarPrepareEventSkill()

    first = skill.compile(CalendarPrepareEventInput(list_input, create))
    second = skill.compile(CalendarPrepareEventInput(list_input, create))

    assert first == second
    assert first.steps[-1].operation_input == create
    assert first.steps[-1].execution_available is False


def test_creation_can_use_default_writable_calendar() -> None:
    plan = CalendarAgent(clock=lambda: REFERENCE_TIME).plan(
        context(
            'Crea un evento "Planificación" mañana a las 10 durante 60 minutos',
            timezone="Europe/Helsinki",
        )
    )

    assert plan.open_questions == ()
    assert [step.tool_reference.operation_id for step in plan.steps] == [
        "list_events",
        "create_event",
    ]
    creation = plan.steps[-1].operation_input
    assert isinstance(creation, CalendarCreateEventInput)
    assert creation.calendar_reference is None
