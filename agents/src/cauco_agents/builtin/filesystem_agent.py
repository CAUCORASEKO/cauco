import re

from cauco_agents.base import AgentMetadata
from cauco_agents.builtin.base import DeterministicSignalAgent
from cauco_agents.models import AgentContext, AgentMatch, AgentPlan, AgentPlanStep, AgentToolReference, AgentRequest, FilesystemWriteTextInput


class FilesystemAgent(DeterministicSignalAgent):
    metadata = AgentMetadata(agent_id="filesystem", name="Workspace Files Agent", description="Recognizes explicit bounded workspace file requests.", version="1.0.0", capabilities=("workspace_listing", "workspace_read", "workspace_write_review"), supported_intents=("filesystem",), priority=30)
    signals = ()

    def can_handle(self, request: AgentRequest) -> AgentMatch:
        normalized = " ".join(request.instruction.casefold().split()).rstrip("?.!,;:")
        matched = requested_workspace_read(request.instruction) is not None or requested_workspace_write(request.instruction) is not None or normalized in {"lista los archivos del workspace", "lista archivos del workspace", "list workspace files", "list the workspace files"}
        return AgentMatch(self.id, matched, 100 if matched else 0, (), ("Matched an exact workspace filesystem request.",) if matched else ("No exact workspace filesystem request matched.",), self.metadata.priority)

    def summary(self) -> str: return "This request concerns the bounded Cauco workspace."
    def proposed_actions(self) -> tuple[str, ...]: return ("Inspect or prepare an explicitly requested workspace path.",)
    def requires_confirmation(self) -> bool: return False

    def plan(self, context: AgentContext, *, allow_execution: bool = False) -> AgentPlan:
        write = requested_workspace_write(context.instruction)
        read = requested_workspace_read(context.instruction)
        if write is not None:
            step = AgentPlanStep(order=1, title="Prepare workspace text write", description="Create an inert preview; no file is written until confirmed.", source_memory_ids=(), proposed_action="Review the proposed workspace text write.", requires_confirmation=True, execution_available=False, warnings=(), tool_reference=AgentToolReference("filesystem", "write_text_file", write.relative_path), operation_input=write)
            return AgentPlan(self.id, self.metadata.name, "proposal_only", "Prepare a confirmed workspace file write.", False, (step,), (), ("No file was changed.",), True, False, {"workspace_operation": "write"})
        operation, target = ("read_file", read) if read is not None else ("list_directory", ".")
        step = AgentPlanStep(order=1, title="Inspect workspace", description="Read only the bounded workspace target.", source_memory_ids=(), proposed_action="Inspect the workspace without changing it.", requires_confirmation=False, execution_available=False, warnings=(), tool_reference=AgentToolReference("filesystem", operation, target))
        return AgentPlan(self.id, self.metadata.name, "proposal_only", "Inspect the Cauco workspace.", False, (step,), (), (), False, False, {"workspace_operation": operation})


_PATH = r"([A-Za-z0-9_-]+(?:/[A-Za-z0-9_.-]+)*\.(?:md|txt|json|ya?ml|toml))"

def requested_workspace_read(instruction: str) -> str | None:
    match = re.fullmatch(r"\s*(?:lee|read)\s+(?:el |the )?(?:archivo |file )?" + _PATH + r"\s*[.?!]?\s*", instruction, re.I)
    return match.group(1) if match else None

def requested_workspace_write(instruction: str) -> FilesystemWriteTextInput | None:
    # Only the initial vocative and the filename accept dictated variants.
    write_path = r"([A-Za-z0-9_-]+(?:/[A-Za-z0-9_.-]+)*(?:\.|\s+punto\s+)(?:md|txt|json|ya?ml|toml))"
    match = re.fullmatch(
        r"\s*(?:(?:Cauco|Cojo)(?:,\s*|\s+))?"
        r"(crea|create|escribe|write|reemplaza|replace)\s+(?:un |a )?(?:archivo |file )?"
        + write_path
        + r"\s+(?:con(?: (?:este )?contenido)?|containing|with)\s*:?\s*(.+)",
        instruction, re.I | re.S,
    )
    if match is None:
        return None
    try:
        policy = "replace_existing" if match.group(1).casefold() in {"reemplaza", "replace"} else "create_only"
        path = re.sub(r"\s+punto\s+(md|txt|json|ya?ml|toml)$", r".\1", match.group(2), flags=re.I)
        return FilesystemWriteTextInput(path, match.group(3), policy)
    except ValueError:
        return None
