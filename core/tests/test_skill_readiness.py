from dataclasses import replace

from cauco_agents import (
    AgentPlan,
    AgentToolReference,
    FilesystemWriteTextInput,
    GitInspectRepositoryInput,
    GitInspectRepositorySkill,
)
from cauco_tools import create_default_registry

from cauco_core.agents.readiness import PlanValidator


def plan_for_steps(steps) -> AgentPlan:
    return AgentPlan(
        agent_id="git",
        agent_name="Git Agent",
        status="proposal_only",
        objective="Validate compiled skill steps.",
        context_used=False,
        steps=steps,
        open_questions=(),
        warnings=(),
        requires_confirmation=True,
    )


def test_skill_output_remains_subject_to_plan_validator() -> None:
    compilation = GitInspectRepositorySkill().compile(
        GitInspectRepositoryInput(source_memory_ids=(), requested_operation="status")
    )
    readiness = PlanValidator(create_default_registry()).validate(
        plan_for_steps(compilation.steps)
    )

    assert readiness.ready is True
    diff = next(item for item in readiness.references if item.operation_id == "diff")
    assert diff.runtime_execution_allowed is False
    assert diff.executable_now is False


def test_skill_cannot_make_unknown_operation_executable() -> None:
    compilation = GitInspectRepositorySkill().compile(
        GitInspectRepositoryInput(source_memory_ids=(), requested_operation="status")
    )
    unknown = replace(
        compilation.steps[0],
        tool_reference=AgentToolReference("git", "unknown_operation"),
    )
    readiness = PlanValidator(create_default_registry()).validate(
        plan_for_steps((unknown, *compilation.steps[1:]))
    )

    assert readiness.ready is False
    reference = readiness.references[0]
    assert reference.operation_exists is False
    assert reference.executable_now is False


def test_compiled_mutation_retains_preview_and_confirmation_semantics() -> None:
    write = FilesystemWriteTextInput("notes.txt", "approved", "create_only")
    compilation = GitInspectRepositorySkill().compile(
        GitInspectRepositoryInput(
            source_memory_ids=(),
            requested_operation="status",
            file_target="notes.txt",
            write_input=write,
        )
    )
    readiness = PlanValidator(create_default_registry()).validate(
        plan_for_steps(compilation.steps)
    )
    mutation = next(item for item in readiness.references if item.operation_id == "write_text_file")

    assert mutation.mutation_confirmation_required is True
    assert mutation.preview_required is True
    assert mutation.executable_now is False
