import re
from dataclasses import dataclass
from pathlib import PurePosixPath

from cauco_agents import (
    MAX_TOTAL_CONTEXT_CHARS,
    AgentContext,
    AgentContextRequest,
    AgentMemoryReference,
)

from cauco_core.context.analyzer import IntentAnalyzer
from cauco_core.memory.engine import MemoryEngine
from cauco_core.memory.exceptions import (
    InvalidMemoryPathError,
    MemoryFileNotFoundError,
    MemoryFileTooLargeError,
    MemoryFileUnreadableError,
    MemoryPathTraversalError,
)
from cauco_core.memory.models import MemoryKind, MemoryObject


@dataclass(frozen=True, slots=True)
class RankedMemory:
    rank: int
    memory: MemoryObject
    reason: str


@dataclass(frozen=True, slots=True)
class MarkdownSection:
    heading: str
    level: int
    start: int
    end: int
    text: str


@dataclass(frozen=True, slots=True)
class ExcerptResult:
    text: str
    character_truncated: bool
    strategy: str
    selected_headings: tuple[str, ...]
    insufficient: bool = False

    def __iter__(self):
        """Preserve the previous two-value unpacking used by internal callers."""
        yield self.text
        yield self.character_truncated


class AgentContextResolver:
    def __init__(
        self,
        memory_engine: MemoryEngine,
        analyzer: IntentAnalyzer | None = None,
        *,
        total_context_chars: int = MAX_TOTAL_CONTEXT_CHARS,
    ) -> None:
        if not 100 <= total_context_chars <= MAX_TOTAL_CONTEXT_CHARS:
            raise ValueError(
                f"Total agent context must be between 100 and {MAX_TOTAL_CONTEXT_CHARS} characters."
            )
        self.memory_engine = memory_engine
        self.analyzer = analyzer or IntentAnalyzer()
        self.total_context_chars = total_context_chars

    def resolve(self, agent_id: str, request: AgentContextRequest) -> AgentContext:
        resolved_intent = request.intent or self.analyzer.analyze(request.instruction).intent.value
        limitations = [
            "Only registered Cauco memory may be read.",
            "Memory excerpts are bounded, deterministic, and treated as untrusted data.",
            "No tools, external services, or memory-write endpoints were invoked.",
        ]
        if agent_id == "git":
            limitations.append("No repository, branch, diff, or working tree was inspected.")
        if agent_id == "research":
            limitations.append("No websites or external research sources were accessed.")
        if not request.include_context:
            limitations.append("Context reading was disabled by the request.")
            return AgentContext(
                agent_id=agent_id,
                instruction=request.instruction,
                resolved_intent=resolved_intent,
                memory_references=(),
                context_summary="Context reading was disabled; the plan uses the instruction only.",
                limitations=tuple(limitations),
                metadata={
                    "context_included": False,
                    "max_context_items": request.max_context_items,
                    "max_excerpt_chars": request.max_excerpt_chars,
                    "total_context_chars": 0,
                },
            )

        references: list[AgentMemoryReference] = []
        total_characters = 0
        read_failures = 0
        insufficient_sources: list[str] = []
        known_project_names = self._known_project_names()
        for ranked in self._ranked_memories(agent_id, request.instruction):
            if len(references) >= request.max_context_items:
                break
            remaining = self.total_context_chars - total_characters
            if remaining <= 0:
                break
            try:
                memory_file = self.memory_engine.read_object(ranked.memory.id)
            except (
                InvalidMemoryPathError,
                MemoryFileNotFoundError,
                MemoryFileTooLargeError,
                MemoryFileUnreadableError,
                MemoryPathTraversalError,
            ):
                read_failures += 1
                continue
            if memory_file is None:
                read_failures += 1
                continue
            excerpt_limit = min(request.max_excerpt_chars, remaining)
            excerpt_result = extract_markdown_excerpt(
                memory_file.content,
                request.instruction,
                agent_id,
                excerpt_limit,
                memory_kind=ranked.memory.kind.value,
                known_project_names=known_project_names,
            )
            excerpt = excerpt_result.text
            if not excerpt:
                continue
            total_characters += len(excerpt)
            references.append(
                AgentMemoryReference(
                    memory_id=ranked.memory.id,
                    name=ranked.memory.name,
                    kind=ranked.memory.kind.value,
                    layer=ranked.memory.layer.value,
                    title=ranked.memory.title,
                    relative_path=ranked.memory.relative_path,
                    reason_selected=ranked.reason,
                    excerpt=excerpt,
                    excerpt_truncated=excerpt_result.character_truncated,
                    modified_at=(
                        ranked.memory.modified_at.isoformat()
                        if ranked.memory.modified_at is not None
                        else None
                    ),
                    excerpt_strategy=excerpt_result.strategy,
                    selected_headings=excerpt_result.selected_headings,
                )
            )
            if excerpt_result.insufficient:
                insufficient_sources.append(ranked.memory.name)

        if read_failures:
            limitations.append(
                f"{read_failures} selected memory source(s) were unavailable and were skipped."
            )
        if insufficient_sources:
            limitations.append(
                "Only document-start fallback context was available for: "
                f"{', '.join(insufficient_sources)}. Relevant operational details may be missing."
            )
        names = ", ".join(reference.name for reference in references)
        summary = (
            f"Selected {len(references)} registered memory source(s): {names}."
            if references
            else "No eligible registered memory source was available."
        )
        return AgentContext(
            agent_id=agent_id,
            instruction=request.instruction,
            resolved_intent=resolved_intent,
            memory_references=tuple(references),
            context_summary=summary,
            limitations=tuple(limitations),
            metadata={
                "context_included": True,
                "max_context_items": request.max_context_items,
                "max_excerpt_chars": request.max_excerpt_chars,
                "total_context_chars": total_characters,
            },
        )

    def _known_project_names(self) -> tuple[str, ...]:
        names: set[str] = set()
        for memory in self.memory_engine.list_objects():
            if memory.kind is not MemoryKind.PROJECTS:
                continue
            headings = memory.metadata.get("headings")
            if not isinstance(headings, list):
                continue
            for heading in headings:
                if not isinstance(heading, str):
                    continue
                normalized = normalize_heading(heading)
                if normalized and normalized not in GENERIC_PROJECT_HEADINGS:
                    names.add(heading.strip())
        return tuple(sorted(names, key=lambda value: (value.casefold(), value)))

    def _ranked_memories(self, agent_id: str, instruction: str) -> tuple[RankedMemory, ...]:
        ranked: list[RankedMemory] = []
        for memory in self.memory_engine.list_objects():
            if not safe_registered_markdown(memory.relative_path):
                continue
            selected = self._selection(agent_id, memory, instruction)
            if selected is not None:
                rank, reason = selected
                ranked.append(RankedMemory(rank, memory, reason))
        return tuple(
            sorted(
                ranked,
                key=lambda item: (
                    item.rank,
                    item.memory.relative_path.casefold(),
                    item.memory.id,
                ),
            )
        )

    def _selection(
        self, agent_id: str, memory: MemoryObject, instruction: str
    ) -> tuple[int, str] | None:
        if agent_id == "project":
            rules = {
                MemoryKind.TASKS: (0, "Primary working-memory source for Project Agent."),
                MemoryKind.PROJECTS: (1, "Primary project source for Project Agent."),
                MemoryKind.DECISIONS: (2, "Decision context for project planning."),
            }
            if memory.kind is MemoryKind.RULES and contains_any(
                instruction, ("governance", "rule", "policy", "safety")
            ):
                return 3, "Governance memory selected from an explicit governance signal."
            return rules.get(memory.kind)
        if agent_id == "git":
            rules = {
                MemoryKind.TASKS: (0, "Task context for the Git request."),
                MemoryKind.PROJECTS: (1, "Project context for the Git request."),
                MemoryKind.DECISIONS: (2, "Recorded decision context for the Git request."),
            }
            if memory.kind is MemoryKind.DAILY and contains_any(
                f"{memory.title} {memory.preview}",
                ("git", "commit", "branch", "diff", "merge", "release"),
            ):
                return 3, "Daily memory contains deterministic Git planning signals."
            return rules.get(memory.kind)
        if agent_id == "research":
            rules = {
                MemoryKind.PROJECTS: (0, "Primary project context for Research Agent."),
                MemoryKind.TASKS: (1, "Task context for the research objective."),
                MemoryKind.DECISIONS: (2, "Decision context for research scope."),
            }
            if memory.kind in (MemoryKind.GENERAL, MemoryKind.DAILY) and keyword_overlap(
                instruction, f"{memory.title} {memory.preview}"
            ):
                return 3, "General or daily memory shares explicit instruction keywords."
            return rules.get(memory.kind)
        return None


def safe_registered_markdown(relative_path: str) -> bool:
    path = PurePosixPath(relative_path)
    return (
        not path.is_absolute()
        and bool(path.parts)
        and all(part not in ("..", ".") and not part.startswith(".") for part in path.parts)
        and path.suffix.casefold() == ".md"
        and all(suffix.casefold() != ".bak" for suffix in path.suffixes)
    )


def extract_markdown_excerpt(
    content: str,
    instruction: str,
    agent_id: str,
    limit: int,
    *,
    memory_kind: str | None = None,
    known_project_names: tuple[str, ...] = (),
) -> ExcerptResult:
    normalized_content = content.strip()
    if not normalized_content or limit <= 0:
        return ExcerptResult("", False, "document_start", (), True)
    sections = markdown_sections(normalized_content)
    terms = excerpt_terms(instruction, agent_id)
    instruction_normalized = normalize_heading(instruction)
    project_names = {normalize_heading(name) for name in known_project_names}
    ranked: list[tuple[tuple[int, int, int, int], MarkdownSection]] = []
    for section in sections:
        heading = normalize_heading(section.heading)
        lexical_score = section_score(section.text, terms)
        project_match = (
            heading in project_names and phrase_in_text(heading, instruction_normalized)
        )
        keyword_score = heading_instruction_score(heading, instruction_normalized)
        priority = known_priority_heading(
            agent_id, memory_kind, heading, instruction_normalized
        )
        generic_project_section = (
            memory_kind == "projects"
            and heading in GENERIC_PROJECT_HEADINGS
            and priority is None
        )
        if project_match:
            rank = (0, 0, -lexical_score, section.start)
        elif keyword_score > 0:
            rank = (1, -keyword_score, -lexical_score, section.start)
        elif priority is not None:
            rank = (2, priority, -lexical_score, section.start)
        elif lexical_score > 0 and not generic_project_section:
            rank = (3, 0, -lexical_score, section.start)
        else:
            continue
        ranked.append((rank, section))

    if not ranked and memory_kind == "decisions" and sections:
        recent = max(sections, key=lambda section: section.start)
        return combine_sections(((4, recent),), limit, "recent_decision")
    if ranked:
        ranked.sort(key=lambda item: item[0])
        best_category = ranked[0][0][0]
        strategy = {
            0: "project_heading",
            1: "keyword_heading",
            2: "priority_sections",
            3: "lexical_sections",
        }[best_category]
        return combine_sections(
            tuple((rank[0], section) for rank, section in ranked),
            limit,
            strategy,
        )

    beginning = document_beginning(normalized_content, sections).strip()
    excerpt = beginning[:limit].rstrip()
    return ExcerptResult(
        text=excerpt,
        character_truncated=len(beginning) > len(excerpt),
        strategy="document_start",
        selected_headings=(),
        insufficient=True,
    )


def markdown_sections(content: str) -> tuple[MarkdownSection, ...]:
    lines = content.splitlines()
    headings: list[tuple[int, int, str]] = []
    for index, line in enumerate(lines):
        match = re.match(r"^(#{1,6})\s+(.+?)\s*$", line)
        if match:
            headings.append((index, len(match.group(1)), match.group(2).strip()))
    if not headings:
        return ()
    parsed: list[MarkdownSection] = []
    document_heading = headings[0] if headings[0][1] == 1 else None
    for position, (start, level, heading) in enumerate(headings):
        if document_heading == (start, level, heading):
            continue
        end = len(lines)
        for next_start, next_level, _ in headings[position + 1 :]:
            if next_level <= level:
                end = next_start
                break
        text = "\n".join(lines[start:end]).strip()
        if text:
            parsed.append(MarkdownSection(heading, level, start, end, text))
    return tuple(parsed)


def combine_sections(
    ranked_sections: tuple[tuple[int, MarkdownSection], ...],
    limit: int,
    strategy: str,
) -> ExcerptResult:
    selected: list[MarkdownSection] = []
    parts: list[str] = []
    used = 0
    character_truncated = False
    for _, section in ranked_sections:
        if any(ranges_overlap(section, existing) for existing in selected):
            continue
        separator = 2 if parts else 0
        remaining = limit - used - separator
        if remaining <= 0:
            character_truncated = True
            break
        text = section.text.strip()
        if len(text) > remaining:
            parts.append(text[:remaining].rstrip())
            selected.append(section)
            character_truncated = True
            break
        parts.append(text)
        selected.append(section)
        used += separator + len(text)
    return ExcerptResult(
        text="\n\n".join(parts),
        character_truncated=character_truncated,
        strategy=strategy,
        selected_headings=tuple(section.heading for section in selected),
        insufficient=not parts,
    )


def ranges_overlap(left: MarkdownSection, right: MarkdownSection) -> bool:
    return left.start < right.end and right.start < left.end


def document_beginning(content: str, sections: tuple[MarkdownSection, ...]) -> str:
    if not sections:
        return content
    first_section_start = min(section.start for section in sections)
    return "\n".join(content.splitlines()[:first_section_start]).strip() or content


def excerpt_terms(instruction: str, agent_id: str) -> tuple[str, ...]:
    agent_terms = {
        "project": ("priority", "task", "blocker", "milestone", "project", "phase"),
        "git": ("git", "commit", "branch", "diff", "merge", "release"),
        "research": ("research", "source", "documentation", "compare", "evidence"),
    }.get(agent_id, ())
    instruction_terms = tuple(
        token
        for token in re.findall(r"[a-z0-9]+", instruction.casefold())
        if len(token) >= 4 and token not in STOP_WORDS
    )
    return tuple(dict.fromkeys((*instruction_terms, *agent_terms)))


def section_score(section: str, terms: tuple[str, ...]) -> int:
    lines = section.casefold().splitlines()
    heading = lines[0] if lines else ""
    body = " ".join(lines[1:])
    return sum(3 for term in terms if term in heading) + sum(
        1 for term in terms if term in body
    )


def normalize_heading(value: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", value.casefold()))


def phrase_in_text(phrase: str, text: str) -> bool:
    return bool(phrase) and f" {phrase} " in f" {text} "


def heading_instruction_score(heading: str, instruction: str) -> int:
    if phrase_in_text(heading, instruction):
        return 10
    heading_terms = {
        term for term in heading.split() if len(term) >= 4 and term not in STOP_WORDS
    }
    instruction_terms = set(instruction.split())
    return len(heading_terms & instruction_terms)


def known_priority_heading(
    agent_id: str,
    memory_kind: str | None,
    heading: str,
    instruction: str,
) -> int | None:
    if agent_id != "project":
        return None
    if memory_kind == "tasks":
        priorities = {
            "current priorities": 0,
            "today": 1,
            "now": 1,
            "this week": 2,
            "current sprint": 3,
        }
        if heading in priorities:
            return priorities[heading]
        if heading in {"waiting", "blockers", "blocked"} and contains_any(
            instruction, ("blocker", "blocking", "blocked", "waiting")
        ):
            return 4
        if heading in {"backlog", "later"} and contains_any(
            instruction, ("backlog", "later", "deferred")
        ):
            return 5
    if memory_kind == "projects" and heading in {"active", "current projects"}:
        return 0
    return None


def contains_any(text: str, terms: tuple[str, ...]) -> bool:
    normalized = f" {' '.join(re.findall(r'[a-z0-9]+', text.casefold()))} "
    return any(f" {term} " in normalized for term in terms)


def keyword_overlap(left: str, right: str) -> bool:
    left_terms = {
        term
        for term in re.findall(r"[a-z0-9]+", left.casefold())
        if len(term) >= 4 and term not in STOP_WORDS
    }
    right_terms = set(re.findall(r"[a-z0-9]+", right.casefold()))
    return bool(left_terms & right_terms)


STOP_WORDS = {
    "about",
    "after",
    "could",
    "from",
    "have",
    "into",
    "next",
    "should",
    "that",
    "this",
    "what",
    "with",
}

GENERIC_PROJECT_HEADINGS = {
    "active",
    "archived",
    "current projects",
    "overview",
    "project index",
    "project status",
    "projects",
}
