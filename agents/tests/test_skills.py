import subprocess
import urllib.request
from dataclasses import FrozenInstanceError, fields, replace

import pytest

from cauco_agents import (
    AgentContext,
    FilesystemWriteTextInput,
    GitAgent,
    GitInspectRepositoryInput,
    GitInspectRepositorySkill,
    SkillCompilation,
    SkillDefinition,
    SkillRegistry,
    create_default_skill_registry,
)


def git_context(instruction: str) -> AgentContext:
    return AgentContext(
        agent_id="git",
        instruction=instruction,
        resolved_intent="git",
        memory_references=(),
        context_summary="No memory context.",
        limitations=("Repository state is unknown.",),
    )


def test_skill_definition_is_validated_and_immutable() -> None:
    definition = GitInspectRepositorySkill.definition
    assert definition.skill_id == "git.inspect_repository"
    assert definition.version == 1
    with pytest.raises(FrozenInstanceError):
        definition.version = 2  # type: ignore[misc]
    with pytest.raises(ValueError, match="version 1"):
        SkillDefinition("git.future", 2, "Future skill.", ("git",))
    with pytest.raises(ValueError, match="lowercase dotted"):
        SkillDefinition("Git Inspect", 1, "Invalid skill.", ("git",))


def test_skill_registry_rejects_duplicates_and_unknown_lookups() -> None:
    registry = SkillRegistry()
    skill = GitInspectRepositorySkill()
    registry.register(skill)

    assert registry.exists("git.inspect_repository") is True
    assert registry.list() == (skill,)
    assert registry.list_definitions() == (skill.definition,)
    with pytest.raises(ValueError, match="already registered"):
        registry.register(GitInspectRepositorySkill())
    with pytest.raises(KeyError, match="Unknown skill"):
        registry.get("git.missing")


def test_git_skill_compilation_is_deterministic_immutable_and_non_executing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def unexpected(*args: object, **kwargs: object) -> None:
        raise AssertionError("Skill compilation attempted external execution.")

    monkeypatch.setattr(subprocess, "run", unexpected)
    monkeypatch.setattr(urllib.request, "urlopen", unexpected)
    input_data = GitInspectRepositoryInput(
        source_memory_ids=("memory_projects",),
        requested_operation="status",
        file_target="README.md",
    )
    skill = GitInspectRepositorySkill()

    first = skill.compile(input_data)
    second = skill.compile(input_data)

    assert first == second
    assert tuple(item.name for item in fields(SkillCompilation)) == (
        "skill_id",
        "skill_version",
        "steps",
        "warnings",
        "open_questions",
    )
    assert first.steps[2].tool_reference.tool_id == "filesystem"
    assert first.steps[2].tool_reference.operation_id == "read_file"
    assert first.steps[2].tool_reference.target == "README.md"
    with pytest.raises(FrozenInstanceError):
        first.skill_version = 2  # type: ignore[misc]


@pytest.mark.parametrize(
    ("instruction", "expected_references"),
    [
        (
            "Inspect git status",
            (
                ("filesystem", "list_directory", "."),
                ("git", "status", None),
                ("git", "diff", None),
                ("git", "status", None),
            ),
        ),
        (
            "Review README.md in the git repository",
            (
                ("filesystem", "list_directory", "."),
                ("git", "status", None),
                ("filesystem", "read_file", "README.md"),
                ("git", "status", None),
            ),
        ),
    ],
)
def test_git_agent_preserves_bounded_recipe_after_skill_refactor(
    instruction: str, expected_references: tuple[tuple[str, str, str | None], ...]
) -> None:
    plan = GitAgent(create_default_skill_registry()).plan(git_context(instruction))

    assert (
        tuple(
            (
                step.tool_reference.tool_id,
                step.tool_reference.operation_id,
                step.tool_reference.target,
            )
            for step in plan.steps
        )
        == expected_references
    )
    assert tuple(step.order for step in plan.steps) == (1, 2, 3, 4)
    assert all(step.execution_available is False for step in plan.steps)


def test_git_skill_preserves_typed_mutation_input_without_fabrication() -> None:
    write = FilesystemWriteTextInput("notes.txt", "approved text", "create_only")
    compilation = GitInspectRepositorySkill().compile(
        GitInspectRepositoryInput(
            source_memory_ids=(),
            requested_operation="status",
            file_target="notes.txt",
            write_input=write,
        )
    )
    mutation = compilation.steps[2]

    assert mutation.operation_input == write
    assert mutation.tool_reference.operation_id == "write_text_file"
    assert mutation.requires_confirmation is False
    assert compilation.steps[3].operation_input is None

    missing = GitInspectRepositorySkill().compile(
        GitInspectRepositoryInput(source_memory_ids=(), requested_operation="commit")
    )
    assert missing.steps[-1].tool_reference.operation_id == "status"
    assert missing.steps[-1].operation_input is None
    assert missing.open_questions


def test_default_registry_contains_calendar_planning_skills_only() -> None:
    registry = create_default_skill_registry()

    assert [item.skill_id for item in registry.list_definitions()] == [
        "calendar.inspect_schedule",
        "calendar.prepare_event",
        "git.inspect_repository",
    ]
    assert registry.exists("calendar.delete_event") is False


def test_git_agent_uses_injected_skill_registry() -> None:
    registry = create_default_skill_registry()
    original = registry.get("git.inspect_repository")
    compilation = original.compile(
        GitInspectRepositoryInput(source_memory_ids=(), requested_operation="status")
    )

    class FixedSkill:
        definition = original.definition

        def compile(self, input_data):
            return replace(compilation, warnings=("Compiled by injected skill.",))

    injected = SkillRegistry()
    injected.register(FixedSkill())
    plan = GitAgent(injected).plan(git_context("Inspect git status"))

    assert "Compiled by injected skill." in plan.warnings
