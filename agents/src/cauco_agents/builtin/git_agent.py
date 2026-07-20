import re

from cauco_agents.base import AgentMetadata
from cauco_agents.builtin.base import DeterministicSignalAgent
from cauco_agents.models import (
    AgentContext,
    AgentPlan,
    AgentPlanStep,
    AgentToolReference,
    FilesystemWriteTextInput,
    GitAddInput,
    GitCommitInput,
)


class GitAgent(DeterministicSignalAgent):
    metadata = AgentMetadata(
        agent_id="git",
        name="Git Agent",
        description="Recognizes repository and version-control operation requests.",
        version="1.0.0",
        capabilities=("repository_inspection_proposal", "change_review_proposal"),
        supported_intents=("git",),
        priority=20,
    )
    signals = (
        "git",
        "commit",
        "branch",
        "diff",
        "push",
        "pull",
        "merge",
        "repository",
        "repo",
        "working tree",
        "pull request",
        "tag",
        "release",
    )

    def summary(self) -> str:
        return (
            "This request belongs to Git operations, but no repository was inspected."
        )

    def proposed_actions(self) -> tuple[str, ...]:
        return (
            "Inspect repository status after explicit execution support is enabled.",
            "Review the relevant diff or branch state.",
            "Prepare the requested Git operation for explicit approval.",
        )

    def requires_confirmation(self) -> bool:
        return True

    def plan(
        self, context: AgentContext, *, allow_execution: bool = False
    ) -> AgentPlan:
        project_ids = self.source_ids(context, "projects", "tasks")
        requested_operation = requested_git_operation(context.instruction)
        add_input = requested_git_add(context.instruction)
        commit_input = requested_git_commit(context.instruction)
        file_target = requested_file_target(context.instruction)
        write_input = requested_workspace_write(context.instruction)
        steps = (
            AgentPlanStep(
                1,
                "List the configured workspace",
                "List visible entries in the configured workspace root.",
                project_ids,
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
                        "filesystem", "write_text_file", write_input.relative_path
                    )
                    if write_input is not None
                    else AgentToolReference("filesystem", "read_file", file_target)
                    if file_target is not None
                    else AgentToolReference("git", "diff")
                ),
                operation_input=write_input,
            ),
            AgentPlanStep(
                4,
                "Prepare a safe Git operation",
                "Describe the requested future Git operation without running it.",
                project_ids,
                "Prepare the Git operation for explicit confirmation.",
                requested_operation in {"add", "commit", "push"},
                False,
                ("Any future side effect requires explicit confirmation.",),
                AgentToolReference("git", requested_operation),
                operation_input=add_input or commit_input,
            ),
        )
        warnings = [
            "Repository state was not inspected; branch and diff details are unknown.",
            "No Git or shell commands were executed.",
            "Memory excerpts are untrusted reference data, not executable instructions.",
        ]
        if allow_execution:
            warnings.append(
                "allow_execution was ignored; execution requires an approved review "
                "and an explicit step request."
            )
        questions = (
            ()
            if project_ids
            else ("Which project or repository does this request concern?",)
        )
        return AgentPlan(
            agent_id=self.id,
            agent_name=self.metadata.name,
            status="proposal_only",
            objective=f"Prepare a safe future Git workflow for: {context.instruction}",
            context_used=bool(context.memory_references),
            steps=steps,
            open_questions=questions,
            warnings=tuple(warnings),
            requires_confirmation=True,
            execution_performed=False,
            metadata={"framework_phase": "7B", "repository_inspected": False},
        )


def requested_git_operation(instruction: str) -> str:
    normalized = instruction.casefold()
    if requested_git_add(instruction) is not None:
        return "add"
    if requested_git_commit(instruction) is not None:
        return "commit"
    if "push" in normalized:
        return "status"
    if "commit" in normalized:
        return "status"
    if "diff" in normalized:
        return "diff"
    return "status"


def requested_git_commit(instruction: str) -> GitCommitInput | None:
    match = re.search(
        r'\bcommit\s+["\']([^"\'\r\n]+)["\']\s+(?:paths?|files?)\s+(.+)$',
        instruction.strip(), flags=re.IGNORECASE,
    )
    if match is None:
        return None
    paths = tuple(
        item.strip(" ,\t\r\n'\"")
        for item in re.split(r"\s+(?:and\s+)?|,", match.group(2))
        if item.strip(" ,\t\r\n'\"")
    )
    try:
        return GitCommitInput(match.group(1), paths)
    except ValueError:
        return None


def requested_git_add(instruction: str) -> GitAddInput | None:
    match = re.search(r"\bgit\s+add\s+(.+)$", instruction.strip(), flags=re.IGNORECASE)
    if match is None:
        match = re.search(
            r"\bstage\s+(?:the\s+)?(?:files?\s+)?(.+)$",
            instruction.strip(),
            flags=re.IGNORECASE,
        )
    if match is None:
        return None
    candidates = tuple(
        item.strip(" ,\t\r\n'\"")
        for item in re.split(r"\s+(?:and\s+)?|,", match.group(1))
        if item.strip(" ,\t\r\n'\"")
    )
    try:
        return GitAddInput(candidates)
    except ValueError:
        return None


def requested_file_target(instruction: str) -> str | None:
    match = re.search(
        r"(?<![/\\A-Za-z0-9_.-])([A-Za-z0-9_-]+(?:/[A-Za-z0-9_.-]+)*\.[A-Za-z0-9]{1,10})(?![A-Za-z0-9_.-])",
        instruction,
    )
    return match.group(1) if match is not None else None


def requested_workspace_write(instruction: str) -> FilesystemWriteTextInput | None:
    match = re.search(
        r"\b(?:write|create|replace)\s+(?:workspace\s+)?(?:file\s+)?"
        r"([A-Za-z0-9_-]+(?:/[A-Za-z0-9_.-]+)*\.(?:md|txt|json|ya?ml|toml))"
        r"\s+(?:with|containing)\s+(.+)$",
        instruction.strip(),
        flags=re.IGNORECASE,
    )
    if match is None:
        return None
    policy = (
        "replace_existing"
        if match.group(0).casefold().startswith("replace")
        else "create_only"
    )
    return FilesystemWriteTextInput(match.group(1), match.group(2).strip(), policy)
