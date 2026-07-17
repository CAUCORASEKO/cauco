import hashlib
import json
import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime

from cauco_core.memory.classifier import normalize_signal
from cauco_core.memory.engine import MemoryEngine
from cauco_core.memory.models import MemoryKind, MemoryLayer
from cauco_core.memory_writing.analyzer import (
    MemoryWriteAnalyzer,
    MemoryWriteProposalError,
)
from cauco_core.memory_writing.models import (
    MemoryWriteOperation,
    MemoryWriteOperationInfo,
    MemoryWriteProposal,
    MemoryWriteRequest,
)

WHITESPACE_PATTERN = re.compile(r"\s+")


@dataclass(frozen=True)
class ApprovedTarget:
    file: str
    kind: MemoryKind
    layer: MemoryLayer


APPROVED_TARGETS = {
    MemoryWriteOperation.ADD_TASK: ApprovedTarget(
        "Tasks.md", MemoryKind.TASKS, MemoryLayer.WORKING
    ),
    MemoryWriteOperation.ADD_DECISION: ApprovedTarget(
        "Decisions.md", MemoryKind.DECISIONS, MemoryLayer.LONG_TERM
    ),
    MemoryWriteOperation.ADD_RELATIONSHIP_NOTE: ApprovedTarget(
        "Relationships.md", MemoryKind.RELATIONSHIPS, MemoryLayer.LONG_TERM
    ),
    MemoryWriteOperation.ADD_PROJECT_NOTE: ApprovedTarget(
        "Projects.md", MemoryKind.PROJECTS, MemoryLayer.LONG_TERM
    ),
}


class MemoryWriteProposalBuilder:
    def __init__(
        self,
        memory_engine: MemoryEngine,
        analyzer: MemoryWriteAnalyzer | None = None,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.memory_engine = memory_engine
        self.analyzer = analyzer or MemoryWriteAnalyzer()
        self.clock = clock or (lambda: datetime.now(tz=UTC))

    def build(self, request: MemoryWriteRequest) -> MemoryWriteProposal:
        analysis = self.analyzer.analyze(request)
        target = APPROVED_TARGETS[analysis.operation]
        created_at = self.clock()
        normalized_instruction = normalize_whitespace(request.instruction)
        section, content, preview, operation_reasons, warnings = self._proposal_parts(
            request,
            analysis.operation,
            created_at.date(),
        )
        if not content:
            raise MemoryWriteProposalError("The instruction does not contain proposal content.")
        reasoning = [
            *analysis.reasoning,
            f"Selected {target.file} from the approved target allowlist.",
            *operation_reasons,
        ]
        proposal_id = stable_proposal_id(
            operation=analysis.operation,
            target_file=target.file,
            target_section=section,
            normalized_content=content,
            markdown_preview=preview,
        )
        return MemoryWriteProposal(
            proposal_id=proposal_id,
            operation=analysis.operation,
            target_file=target.file,
            target_kind=target.kind,
            target_layer=target.layer,
            target_section=section,
            normalized_content=content,
            markdown_preview=preview,
            original_instruction=normalized_instruction,
            reasoning=reasoning,
            warnings=warnings,
            requires_confirmation=True,
            created_at=created_at,
        )

    def supported_operations(self) -> list[MemoryWriteOperationInfo]:
        return [
            MemoryWriteOperationInfo(operation=operation, target_file=target.file)
            for operation, target in APPROVED_TARGETS.items()
        ]

    def _proposal_parts(
        self,
        request: MemoryWriteRequest,
        operation: MemoryWriteOperation,
        current_date: date,
    ) -> tuple[str, str, str, list[str], list[str]]:
        if operation is MemoryWriteOperation.ADD_TASK:
            return self._task_parts(request)
        if operation is MemoryWriteOperation.ADD_DECISION:
            return self._decision_parts(request, current_date)
        if operation is MemoryWriteOperation.ADD_RELATIONSHIP_NOTE:
            return self._relationship_parts(request)
        return self._project_parts(request)

    def _task_parts(
        self, request: MemoryWriteRequest
    ) -> tuple[str, str, str, list[str], list[str]]:
        folded = normalize_signal(request.instruction)
        if any(signal in folded.split() for signal in ("someday", "later", "backlog")) or (
            "not urgent" in folded
        ):
            section = "Backlog"
            section_reason = "Selected Backlog from an explicit deferred-work signal."
        elif "this week" in folded or "tomorrow" in folded:
            section = "This Week"
            section_reason = "Selected This Week from a tomorrow or weekly planning signal."
        else:
            section = "Today"
            section_reason = "Selected Today for current planning."
        content = _task_content(request.instruction)
        if request.requested_date is not None:
            content = f"{content} ({request.requested_date.isoformat()})"
        return section, content, f"- [ ] {content}", [section_reason], []

    def _decision_parts(
        self,
        request: MemoryWriteRequest,
        current_date: date,
    ) -> tuple[str, str, str, list[str], list[str]]:
        content = _strip_leading_request(
            request.instruction,
            (
                r"record\s+the\s+decision\s+that\s+",
                r"add\s+(?:a\s+)?decision\s+(?:that\s+)?",
                r"decision\s*:\s*",
            ),
        )
        decision_text, impact = _split_impact(content)
        decision, reason = _split_reason(decision_text)
        decision_date = request.requested_date or current_date
        reason_text = reason or "[Not supplied]"
        impact_text = impact or "[To be reviewed]"
        preview = (
            f"- **Date:** {decision_date.isoformat()}\n"
            f"  - **Decision:** {decision}\n"
            f"  - **Reason:** {reason_text}\n"
            f"  - **Impact:** {impact_text}"
        )
        warnings = [] if reason else ["No explicit reason was supplied; review the placeholder."]
        if impact is None:
            warnings.append("Decision impact requires human review.")
        return (
            "Decision Log",
            decision,
            preview,
            ["Selected Decision Log for recorded rationale."],
            warnings,
        )

    def _relationship_parts(
        self, request: MemoryWriteRequest
    ) -> tuple[str, str, str, list[str], list[str]]:
        content = _strip_leading_request(
            request.instruction,
            (
                r"add\s+(?:a\s+)?(?:relationship\s+)?note\s+that\s+",
                r"remember\s+that\s+",
            ),
        )
        person = request.person or _infer_person(content)
        if person and normalize_signal(content).startswith(normalize_signal(person)):
            detail = content[len(person) :].lstrip(" :-")
            detail = _sentence_case(detail)
            preview = f"- **{person}:** {detail}"
        elif person:
            preview = f"- **{person}:** {content}"
        else:
            preview = f"- {content}"
        warnings = [] if person else ["No person was supplied or deterministically detected."]
        return (
            "Personal Notes",
            content,
            preview,
            ["Selected Personal Notes for relationship context."],
            warnings,
        )

    def _project_parts(
        self, request: MemoryWriteRequest
    ) -> tuple[str, str, str, list[str], list[str]]:
        content = _strip_leading_request(
            request.instruction,
            (
                r"add\s+to\s+(?:the\s+)?[^.]+?\s+project\s+that\s+",
                r"add\s+(?:a\s+)?project\s+note\s+(?:that\s+)?",
            ),
        )
        project = request.project or _infer_project(request.instruction)
        matched_heading = self._matching_project_heading(project)
        warnings: list[str] = []
        if matched_heading:
            section = matched_heading
            section_reason = f"Matched approved existing project heading: {matched_heading}."
        else:
            section = "Project Notes"
            if project:
                warnings.append(
                    f"No existing project heading matched '{project}'; using Project Notes."
                )
            else:
                warnings.append("No project was supplied or deterministically detected.")
            section_reason = "Selected the approved Project Notes fallback section."
        preview = f"- **{project}:** {content}" if project else f"- {content}"
        return section, content, preview, [section_reason], warnings

    def _matching_project_heading(self, project: str | None) -> str | None:
        if not project:
            return None
        normalized_project = normalize_signal(project)
        for memory in self.memory_engine.list_objects():
            if memory.relative_path.casefold() != "projects.md":
                continue
            headings = memory.metadata.get("headings", [])
            if not isinstance(headings, list):
                continue
            for heading in headings:
                if (
                    isinstance(heading, str)
                    and normalize_signal(heading) == normalized_project
                    and normalize_signal(heading) != "projects"
                ):
                    return heading
        return None


def normalize_whitespace(value: str) -> str:
    return WHITESPACE_PATTERN.sub(" ", value).strip()


def stable_proposal_id(
    *,
    operation: MemoryWriteOperation,
    target_file: str,
    target_section: str,
    normalized_content: str,
    markdown_preview: str,
) -> str:
    canonical = json.dumps(
        {
            "operation": operation.value,
            "target_file": target_file,
            "target_section": target_section,
            "normalized_content": normalized_content,
            "markdown_preview": markdown_preview,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:24]
    return f"proposal_{digest}"


def _task_content(instruction: str) -> str:
    content = normalize_whitespace(instruction).rstrip(" .")
    content = re.sub(r"^remember\s+that\s+", "", content, flags=re.IGNORECASE)
    temporal = ""
    if re.match(r"^tomorrow\b", content, flags=re.IGNORECASE):
        content = re.sub(r"^tomorrow\s+", "", content, flags=re.IGNORECASE)
        temporal = " tomorrow"
    content = re.sub(
        r"^(?:i\s+)?(?:must|need\s+to|have\s+to|should)\s+",
        "",
        content,
        flags=re.IGNORECASE,
    )
    content = re.sub(
        r"^(?:add\s+(?:a\s+)?task(?:\s+to)?\s*|todo\s*:?\s*)",
        "",
        content,
        flags=re.IGNORECASE,
    )
    return _sentence_case(f"{content}{temporal}")


def _strip_leading_request(value: str, patterns: tuple[str, ...]) -> str:
    content = normalize_whitespace(value).rstrip(" .")
    for pattern in patterns:
        updated = re.sub(f"^{pattern}", "", content, flags=re.IGNORECASE)
        if updated != content:
            content = updated
            break
    return _sentence_case(content)


def _split_reason(content: str) -> tuple[str, str | None]:
    match = re.search(r"\s+(?:because|due to|so that)\s+", content, flags=re.IGNORECASE)
    if match is None:
        return content, None
    decision = content[: match.start()].rstrip(" ,")
    reason = _sentence_case(content[match.end() :])
    return decision, reason


def _split_impact(content: str) -> tuple[str, str | None]:
    match = re.search(
        r"\s+(?:impact\s*:|resulting in|which will)\s+",
        content,
        flags=re.IGNORECASE,
    )
    if match is None:
        return content, None
    decision = content[: match.start()].rstrip(" ,")
    impact = _sentence_case(content[match.end() :])
    return decision, impact


def _infer_person(content: str) -> str | None:
    match = re.match(r"([A-ZÀ-ÖØ-Ý][\wÀ-ÖØ-öø-ÿ'-]{1,79})\b", content)
    return match.group(1) if match else None


def _infer_project(instruction: str) -> str | None:
    normalized = normalize_whitespace(instruction)
    match = re.search(
        r"(?:add\s+to|for)\s+(?:the\s+)?([A-Za-zÀ-ÖØ-öø-ÿ0-9][\wÀ-ÖØ-öø-ÿ -]{0,79}?)\s+project\b",
        normalized,
        flags=re.IGNORECASE,
    )
    return _sentence_case(match.group(1)) if match else None


def _sentence_case(value: str) -> str:
    normalized = normalize_whitespace(value).strip(" .")
    if not normalized:
        return ""
    return f"{normalized[0].upper()}{normalized[1:]}"
