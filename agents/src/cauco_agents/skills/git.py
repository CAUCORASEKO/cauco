from dataclasses import dataclass

from cauco_agents.models import (
    AgentPlanStep,
    AgentToolReference,
    FilesystemWriteTextInput,
    GitAddInput,
    GitCommitInput,
)
from cauco_agents.skills.models import SkillCompilation, SkillDefinition


@dataclass(frozen=True, slots=True)
class GitInspectRepositoryInput:
    source_memory_ids: tuple[str, ...]
    requested_operation: str
    file_target: str | None = None
    write_input: FilesystemWriteTextInput | None = None
    add_input: GitAddInput | None = None
    commit_input: GitCommitInput | None = None

    def __post_init__(self) -> None:
        if self.requested_operation not in {"status", "diff", "add", "commit", "push"}:
            raise ValueError("Git skill operation is not part of the bounded recipe.")
        object.__setattr__(self, "source_memory_ids", tuple(self.source_memory_ids))


class GitInspectRepositorySkill:
    definition = SkillDefinition(
        skill_id="git.inspect_repository",
        version=1,
        description="Compile a bounded repository inspection and Git preparation recipe.",
        supported_agent_ids=("git",),
    )

    def compile(self, input_data: GitInspectRepositoryInput) -> SkillCompilation:
        requested_operation = input_data.requested_operation
        open_questions: tuple[str, ...] = ()
        operation_input = input_data.add_input or input_data.commit_input
        if requested_operation == "add" and input_data.add_input is None:
            requested_operation = "status"
            operation_input = None
            open_questions = ("Which exact workspace-relative files should be staged?",)
        elif requested_operation == "commit" and input_data.commit_input is None:
            requested_operation = "status"
            operation_input = None
            open_questions = (
                "What exact commit message and staged file paths should be approved?",
            )
        elif requested_operation == "push":
            requested_operation = "status"
            operation_input = None
            open_questions = (
                "Which exact approved local commit and remote branch should be published?",
            )
        steps = (
            AgentPlanStep(
                1,
                "List the configured workspace",
                "List visible entries in the configured workspace root.",
                input_data.source_memory_ids,
                "Inspect the workspace directory without following hidden entries.",
                False,
                False,
                tool_reference=AgentToolReference("filesystem", "list_directory", "."),
            ),
            AgentPlanStep(
                2,
                "Propose repository status inspection",
                "Repository state is unknown because no repository or working tree was inspected.",
                (),
                "Request explicit permission for a future repository status inspection.",
                False,
                False,
                ("No commands were executed.",),
                AgentToolReference("git", "status"),
            ),
            AgentPlanStep(
                3,
                "Inspect an explicitly named file or propose diff review",
                "Only an exact workspace-relative file named in the instruction can be read.",
                (),
                "Read the explicitly named text file; otherwise leave diff inspection disabled.",
                False,
                False,
                tool_reference=(
                    AgentToolReference(
                        "filesystem", "write_text_file", input_data.write_input.relative_path
                    )
                    if input_data.write_input is not None
                    else AgentToolReference("filesystem", "read_file", input_data.file_target)
                    if input_data.file_target is not None
                    else AgentToolReference("git", "diff")
                ),
                operation_input=input_data.write_input,
            ),
            AgentPlanStep(
                4,
                "Prepare a safe Git operation",
                "Describe the requested future Git operation without running it.",
                input_data.source_memory_ids,
                "Prepare the Git operation for explicit confirmation.",
                requested_operation in {"add", "commit", "push"},
                False,
                ("Any future side effect requires explicit confirmation.",),
                AgentToolReference("git", requested_operation),
                operation_input=operation_input,
            ),
        )
        return SkillCompilation(
            skill_id=self.definition.skill_id,
            skill_version=self.definition.version,
            steps=steps,
            open_questions=open_questions,
        )
