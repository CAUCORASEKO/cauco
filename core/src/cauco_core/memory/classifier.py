import re
import unicodedata
from dataclasses import dataclass
from pathlib import PurePosixPath

from cauco_core.memory.models import MemoryKind, MemoryLayer

FRONT_MATTER_BOUNDARY = "---"
HEADING_PATTERN = re.compile(r"^\s{0,3}#{1,6}\s+(.+?)\s*$")
PREVIEW_WHITESPACE = re.compile(r"\s+")

FILENAME_SIGNALS: dict[str, tuple[MemoryKind, MemoryLayer]] = {
    "bienvenido": (MemoryKind.IDENTITY, MemoryLayer.IDENTITY),
    "welcome": (MemoryKind.IDENTITY, MemoryLayer.IDENTITY),
    "personality": (MemoryKind.IDENTITY, MemoryLayer.IDENTITY),
    "identity": (MemoryKind.IDENTITY, MemoryLayer.IDENTITY),
    "projects": (MemoryKind.PROJECTS, MemoryLayer.LONG_TERM),
    "proyectos": (MemoryKind.PROJECTS, MemoryLayer.LONG_TERM),
    "tasks": (MemoryKind.TASKS, MemoryLayer.WORKING),
    "tareas": (MemoryKind.TASKS, MemoryLayer.WORKING),
    "decisions": (MemoryKind.DECISIONS, MemoryLayer.LONG_TERM),
    "decisiones": (MemoryKind.DECISIONS, MemoryLayer.LONG_TERM),
    "relationships": (MemoryKind.RELATIONSHIPS, MemoryLayer.LONG_TERM),
    "people": (MemoryKind.RELATIONSHIPS, MemoryLayer.LONG_TERM),
    "personas": (MemoryKind.RELATIONSHIPS, MemoryLayer.LONG_TERM),
    "memory rules": (MemoryKind.RULES, MemoryLayer.GOVERNANCE),
    "rules": (MemoryKind.RULES, MemoryLayer.GOVERNANCE),
}

DIRECTORY_SIGNALS: dict[str, tuple[MemoryKind, MemoryLayer]] = {
    "daily": (MemoryKind.DAILY, MemoryLayer.WORKING),
    "diario": (MemoryKind.DAILY, MemoryLayer.WORKING),
    "meetings": (MemoryKind.MEETINGS, MemoryLayer.WORKING),
    "reuniones": (MemoryKind.MEETINGS, MemoryLayer.WORKING),
    "research": (MemoryKind.RESEARCH, MemoryLayer.LONG_TERM),
    "investigacion": (MemoryKind.RESEARCH, MemoryLayer.LONG_TERM),
    "reports": (MemoryKind.REPORTS, MemoryLayer.LONG_TERM),
    "informes": (MemoryKind.REPORTS, MemoryLayer.LONG_TERM),
}

TEXT_KIND_SIGNALS: dict[str, MemoryKind] = {
    **{key: value[0] for key, value in FILENAME_SIGNALS.items()},
    **{key: value[0] for key, value in DIRECTORY_SIGNALS.items()},
    "meeting notes": MemoryKind.MEETINGS,
    "research notes": MemoryKind.RESEARCH,
    "daily note": MemoryKind.DAILY,
}


@dataclass(frozen=True)
class Classification:
    kind: MemoryKind
    layer: MemoryLayer
    confidence: float
    reasons: list[str]
    front_matter: dict[str, str]
    headings: list[str]


def normalize_signal(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value)
    ascii_like = "".join(
        character for character in decomposed if not unicodedata.combining(character)
    )
    return " ".join(re.findall(r"[^\W_]+", ascii_like.casefold(), flags=re.UNICODE))


def parse_front_matter(content: str) -> dict[str, str]:
    lines = content.splitlines()
    if not lines or lines[0].strip() != FRONT_MATTER_BOUNDARY:
        return {}
    metadata: dict[str, str] = {}
    for line in lines[1:]:
        if line.strip() == FRONT_MATTER_BOUNDARY:
            return metadata
        if not line.strip() or line.lstrip().startswith("#") or ":" not in line:
            continue
        key, value = line.split(":", 1)
        normalized_key = key.strip().casefold().replace("-", "_")
        scalar = value.strip().strip("'\"")
        if normalized_key and scalar:
            metadata[normalized_key] = scalar
    return {}


def markdown_headings(content: str) -> list[str]:
    headings: list[str] = []
    in_front_matter = content.startswith(f"{FRONT_MATTER_BOUNDARY}\n")
    for index, line in enumerate(content.splitlines()):
        if in_front_matter:
            if index > 0 and line.strip() == FRONT_MATTER_BOUNDARY:
                in_front_matter = False
            continue
        match = HEADING_PATTERN.match(line)
        if match:
            headings.append(match.group(1).strip())
    return headings


def classify_memory(relative_path: str, title: str, content: str) -> Classification:
    path = PurePosixPath(relative_path)
    normalized_stem = normalize_signal(path.stem)
    normalized_directories = [normalize_signal(part) for part in path.parts[:-1]]
    front_matter = parse_front_matter(content)
    headings = markdown_headings(content)
    kind: MemoryKind | None = None
    layer: MemoryLayer | None = None
    reasons: list[str] = []
    confidence = 0.35

    raw_kind = normalize_signal(front_matter.get("memory_kind", "")).replace(" ", "_")
    raw_layer = normalize_signal(front_matter.get("memory_layer", "")).replace(" ", "_")
    has_explicit_layer = raw_layer in MemoryLayer._value2member_map_
    if raw_kind in MemoryKind._value2member_map_:
        kind = MemoryKind(raw_kind)
        reasons.append("front matter memory_kind")
        confidence = 1.0
    if raw_layer in MemoryLayer._value2member_map_:
        layer = MemoryLayer(raw_layer)
        reasons.append("front matter memory_layer")
        confidence = 1.0

    filename_signal = FILENAME_SIGNALS.get(normalized_stem)
    if filename_signal:
        if kind is None:
            kind = filename_signal[0]
            reasons.append(f"known filename: {path.name}")
        if layer is None:
            layer = filename_signal[1]
            reasons.append(f"known filename layer: {path.name}")
        confidence = max(confidence, 0.95)

    archive_directory = next(
        (part for part in normalized_directories if part in {"archive", "archivo"}), None
    )
    if archive_directory and not has_explicit_layer:
        layer = MemoryLayer.ARCHIVE
        reasons.append(f"archive directory: {archive_directory}")
        confidence = max(confidence, 0.9)

    for directory in reversed(normalized_directories):
        signal = DIRECTORY_SIGNALS.get(directory)
        if signal is None:
            continue
        if kind is None:
            kind = signal[0]
            reasons.append(f"known directory: {directory}")
        if layer is None:
            layer = signal[1]
            reasons.append(f"known directory layer: {directory}")
        confidence = max(confidence, 0.85)
        break

    normalized_text_signals = [
        normalize_signal(title),
        *(normalize_signal(item) for item in headings),
    ]
    for text_signal in normalized_text_signals:
        matched_kind = TEXT_KIND_SIGNALS.get(text_signal)
        if matched_kind is None:
            continue
        if kind is None:
            kind = matched_kind
            reasons.append(f"title or heading signal: {text_signal}")
            confidence = max(confidence, 0.75)
        break

    kind = kind or MemoryKind.GENERAL
    if not reasons:
        reasons.append("default Markdown document")
    if layer is None:
        layer = _default_layer(kind)
        reasons.append(f"default layer for {kind.value}")
    return Classification(kind, layer, confidence, reasons, front_matter, headings)


def _default_layer(kind: MemoryKind) -> MemoryLayer:
    if kind in {MemoryKind.TASKS, MemoryKind.DAILY, MemoryKind.MEETINGS}:
        return MemoryLayer.WORKING
    if kind is MemoryKind.IDENTITY:
        return MemoryLayer.IDENTITY
    if kind is MemoryKind.RULES:
        return MemoryLayer.GOVERNANCE
    if kind is MemoryKind.UNKNOWN:
        return MemoryLayer.UNKNOWN
    return MemoryLayer.LONG_TERM


def normalized_preview(content: str, limit: int = 240) -> str:
    without_front_matter = content
    lines = content.splitlines()
    if lines and lines[0].strip() == FRONT_MATTER_BOUNDARY:
        for index, line in enumerate(lines[1:], start=1):
            if line.strip() == FRONT_MATTER_BOUNDARY:
                without_front_matter = "\n".join(lines[index + 1 :])
                break
    preview = PREVIEW_WHITESPACE.sub(" ", without_front_matter).strip()
    return preview if len(preview) <= limit else f"{preview[: limit - 1].rstrip()}…"
