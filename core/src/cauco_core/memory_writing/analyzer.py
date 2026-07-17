import re
from dataclasses import dataclass
from urllib.parse import unquote

from cauco_core.memory.classifier import normalize_signal
from cauco_core.memory_writing.models import MemoryWriteOperation, MemoryWriteRequest

HTML_PATTERN = re.compile(r"</?[A-Za-z][^>]*>|<!--", flags=re.IGNORECASE)
MARKDOWN_FILE_PATTERN = re.compile(r"(?:^|\s)[^\s]+\.md\b", flags=re.IGNORECASE)
PATH_PATTERN = re.compile(r"(?:^|\s)(?:\.{1,2}[/\\]|[/\\]|[A-Za-z]:[/\\])\S*")
BYPASS_PATTERN = re.compile(
    r"\b(?:without confirmation|skip confirmation|bypass confirmation|do not ask|apply now)\b",
    flags=re.IGNORECASE,
)

INFERENCE_RULES: tuple[tuple[MemoryWriteOperation, tuple[str, ...]], ...] = (
    (
        MemoryWriteOperation.ADD_DECISION,
        ("record the decision", "decision", "decided", "we chose", "we choose"),
    ),
    (
        MemoryWriteOperation.ADD_RELATIONSHIP_NOTE,
        ("relationship", "relationships", "works at", "works with", "person", "people"),
    ),
    (
        MemoryWriteOperation.ADD_PROJECT_NOTE,
        ("project", "phase", "milestone", "project note"),
    ),
    (
        MemoryWriteOperation.ADD_TASK,
        (
            "add a task",
            "task",
            "todo",
            "must",
            "need to",
            "have to",
            "finish",
            "tomorrow",
            "this week",
            "backlog",
        ),
    ),
)


class MemoryWriteProposalError(ValueError):
    """Raised when an instruction cannot safely produce a proposal."""


class UnsafeMemoryWriteInstructionError(MemoryWriteProposalError):
    """Raised when untrusted input contains a prohibited construct."""


class UnsupportedMemoryWriteOperationError(MemoryWriteProposalError):
    """Raised when no supported operation can be selected."""


@dataclass(frozen=True)
class MemoryWriteAnalysis:
    operation: MemoryWriteOperation
    reasoning: list[str]


class MemoryWriteAnalyzer:
    def analyze(self, request: MemoryWriteRequest) -> MemoryWriteAnalysis:
        validate_untrusted_text(request.instruction, field="instruction")
        if request.project is not None:
            validate_untrusted_text(request.project, field="project")
        if request.person is not None:
            validate_untrusted_text(request.person, field="person")

        if request.operation is not None:
            return MemoryWriteAnalysis(
                operation=request.operation,
                reasoning=[f"Used explicit supported operation: {request.operation.value}."],
            )

        normalized = normalize_signal(request.instruction)
        scores: list[tuple[int, MemoryWriteOperation, list[str]]] = []
        for operation, keywords in INFERENCE_RULES:
            matches = [keyword for keyword in keywords if _contains(normalized, keyword)]
            score = sum(2 if " " in keyword else 1 for keyword in matches)
            if operation is MemoryWriteOperation.ADD_PROJECT_NOTE and request.project:
                score += 3
                matches.append("project field")
            if operation is MemoryWriteOperation.ADD_RELATIONSHIP_NOTE and request.person:
                score += 3
                matches.append("person field")
            scores.append((score, operation, matches))
        best_score, best_operation, matches = max(scores, key=lambda item: item[0])
        if best_score == 0:
            raise UnsupportedMemoryWriteOperationError(
                "The instruction does not match a supported memory write operation."
            )
        return MemoryWriteAnalysis(
            operation=best_operation,
            reasoning=[
                f"Detected {best_operation.value} from deterministic signals: "
                f"{', '.join(matches)}."
            ],
        )


def validate_untrusted_text(value: str, *, field: str) -> None:
    decoded = unquote(value)
    if "\x00" in decoded:
        raise UnsafeMemoryWriteInstructionError(f"The {field} contains a null byte.")
    if any(line.strip() == "---" for line in decoded.splitlines()):
        raise UnsafeMemoryWriteInstructionError(
            f"The {field} contains a Markdown front-matter boundary."
        )
    if HTML_PATTERN.search(decoded):
        raise UnsafeMemoryWriteInstructionError(f"The {field} contains HTML markup.")
    if PATH_PATTERN.search(decoded) or MARKDOWN_FILE_PATTERN.search(decoded):
        raise UnsafeMemoryWriteInstructionError(
            f"The {field} attempts to select a file or filesystem path."
        )
    if BYPASS_PATTERN.search(decoded):
        raise UnsafeMemoryWriteInstructionError(
            f"The {field} attempts to bypass required human confirmation."
        )


def _contains(normalized_instruction: str, keyword: str) -> bool:
    return f" {keyword} " in f" {normalized_instruction} "
