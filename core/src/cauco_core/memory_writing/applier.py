import os
import re
import stat
import tempfile
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from threading import Lock

from cauco_core.memory.classifier import normalize_signal
from cauco_core.memory.engine import MemoryEngine
from cauco_core.memory.exceptions import MemoryFileTooLargeError, MemoryFileUnreadableError
from cauco_core.memory_writing.models import (
    MemoryWriteApplicationResult,
    MemoryWriteProposal,
    MemoryWriteProposalState,
)
from cauco_core.memory_writing.proposal_builder import APPROVED_TARGETS, stable_proposal_id
from cauco_core.memory_writing.store import MemoryWriteProposalStore

HEADING_PATTERN = re.compile(r"^(#{1,6})\s+(.+?)\s*$")


class MemoryWriteApplicationError(RuntimeError):
    """Base class for safe proposal application failures."""


class InvalidProposalIntegrityError(MemoryWriteApplicationError):
    """Raised when stored proposal data does not match its stable ID or allowlist."""


class MissingApprovedTargetError(MemoryWriteApplicationError):
    """Raised when the approved target is absent from the registry."""


class MissingApprovedSectionError(MemoryWriteApplicationError):
    """Raised when the approved heading does not exist in the target document."""


class DuplicateMemoryContentError(MemoryWriteApplicationError):
    """Raised when the exact proposal preview already exists in the target section."""


class MemoryWriteProposalApplier:
    def __init__(
        self,
        memory_engine: MemoryEngine,
        store: MemoryWriteProposalStore,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.memory_engine = memory_engine
        self.store = store
        self.clock = clock or (lambda: datetime.now(tz=UTC))
        self._application_lock = Lock()

    def apply(self, proposal_id: str) -> MemoryWriteApplicationResult:
        with self._application_lock:
            stored = self.store.get_pending(proposal_id)
            proposal = stored.proposal
            self._verify_integrity(proposal)
            target = self._resolve_registered_target(proposal)
            target_path = self.memory_engine.memory_service.resolve_approved_write_target(
                target.relative_path
            )
            try:
                original_bytes = target_path.read_bytes()
                if len(original_bytes) > self.memory_engine.memory_service.max_file_size:
                    raise MemoryFileTooLargeError("Approved memory target exceeds the read limit.")
                original_content = original_bytes.decode("utf-8")
            except UnicodeError as error:
                raise MemoryFileUnreadableError(
                    "Approved memory target is not readable UTF-8 text."
                ) from error
            except OSError as error:
                raise MemoryFileUnreadableError(
                    "Approved memory target could not be read."
                ) from error
            updated = insert_under_heading(
                original_content,
                proposal.target_section,
                proposal.markdown_preview,
            )
            atomic_replace_with_backup(target_path, updated, original_bytes)
            applied_at = self.clock()
            self.store.mark_applied(proposal_id, applied_at)
            refreshed = False
            warnings: list[str] = []
            try:
                self.memory_engine.refresh()
                refreshed = any(
                    item.relative_path == target.relative_path
                    for item in self.memory_engine.list_objects()
                )
                if not refreshed:
                    warnings.append(
                        "Memory was written, but the target was not rediscovered after refresh."
                    )
            except Exception:
                warnings.append("Memory was written, but the Memory Engine refresh failed.")
            return MemoryWriteApplicationResult(
                proposal_id=proposal.proposal_id,
                state=MemoryWriteProposalState.APPLIED,
                operation=proposal.operation,
                target_file=proposal.target_file,
                target_section=proposal.target_section,
                applied_markdown=proposal.markdown_preview,
                memory_refreshed=refreshed,
                applied_at=applied_at,
                warnings=warnings,
            )

    @staticmethod
    def _verify_integrity(proposal: MemoryWriteProposal) -> None:
        expected_target = APPROVED_TARGETS.get(proposal.operation)
        if (
            expected_target is None
            or proposal.target_file != expected_target.file
            or proposal.target_kind is not expected_target.kind
            or proposal.target_layer is not expected_target.layer
            or proposal.requires_confirmation is not True
        ):
            raise InvalidProposalIntegrityError(
                "Stored proposal data does not match the approved operation mapping."
            )
        expected_id = stable_proposal_id(
            operation=proposal.operation,
            target_file=proposal.target_file,
            target_section=proposal.target_section,
            normalized_content=proposal.normalized_content,
            markdown_preview=proposal.markdown_preview,
        )
        if expected_id != proposal.proposal_id:
            raise InvalidProposalIntegrityError("Stored proposal integrity verification failed.")

    def _resolve_registered_target(self, proposal: MemoryWriteProposal):
        matches = [
            memory
            for memory in self.memory_engine.list_objects()
            if memory.relative_path == proposal.target_file
        ]
        if len(matches) != 1:
            raise MissingApprovedTargetError(
                "The approved target file is not available in the Memory Engine registry."
            )
        target = matches[0]
        if target.kind is not proposal.target_kind or target.layer is not proposal.target_layer:
            raise InvalidProposalIntegrityError(
                "The registered target classification does not match the proposal."
            )
        return target


def insert_under_heading(content: str, section: str, markdown: str) -> str:
    newline = "\r\n" if "\r\n" in content else "\n"
    lines = content.splitlines()
    heading_index: int | None = None
    heading_level = 0
    for index, line in enumerate(lines):
        match = HEADING_PATTERN.match(line)
        if match and normalize_signal(match.group(2)) == normalize_signal(section):
            heading_index = index
            heading_level = len(match.group(1))
            break
    if heading_index is None:
        raise MissingApprovedSectionError("The approved target section does not exist.")

    section_end = len(lines)
    for index in range(heading_index + 1, len(lines)):
        match = HEADING_PATTERN.match(lines[index])
        if match and len(match.group(1)) <= heading_level:
            section_end = index
            break

    preview_lines = markdown.splitlines()
    section_lines = lines[heading_index + 1 : section_end]
    if _contains_line_sequence(section_lines, preview_lines):
        raise DuplicateMemoryContentError(
            "The exact proposed Markdown is already present in the target section."
        )

    body_end = section_end
    while body_end > heading_index + 1 and not lines[body_end - 1].strip():
        body_end -= 1
    updated_lines = lines[:body_end]
    if updated_lines and updated_lines[-1].strip():
        updated_lines.append("")
    updated_lines.extend(preview_lines)
    suffix = lines[section_end:]
    while suffix and not suffix[0].strip():
        suffix.pop(0)
    if suffix:
        updated_lines.append("")
        updated_lines.extend(suffix)
    result = newline.join(updated_lines)
    if content.endswith(("\n", "\r")):
        result += newline
    return result


def _contains_line_sequence(lines: list[str], expected: list[str]) -> bool:
    if not expected:
        return True
    return any(
        lines[index : index + len(expected)] == expected
        for index in range(len(lines) - len(expected) + 1)
    )


def atomic_replace_with_backup(
    target: Path,
    updated_content: str,
    expected_original: bytes,
) -> None:
    try:
        original_bytes = target.read_bytes()
        if original_bytes != expected_original:
            raise MemoryWriteApplicationError(
                "The approved memory file changed while the proposal was being applied."
            )
        file_mode = stat.S_IMODE(target.stat().st_mode)
    except OSError as error:
        raise MemoryWriteApplicationError("The approved memory file could not be read.") from error

    backup_path = target.with_name(f"{target.name}.bak")
    backup_temp: Path | None = None
    target_temp: Path | None = None
    try:
        backup_temp = _write_temporary(
            target.parent,
            f".{target.name}.bak.",
            original_bytes,
            file_mode,
        )
        os.replace(backup_temp, backup_path)
        backup_temp = None
        target_temp = _write_temporary(
            target.parent,
            f".{target.name}.",
            updated_content.encode("utf-8"),
            file_mode,
        )
        os.replace(target_temp, target)
        target_temp = None
        _fsync_directory(target.parent)
    except OSError as error:
        raise MemoryWriteApplicationError(
            "The approved memory file could not be replaced."
        ) from error
    finally:
        for temporary_path in (backup_temp, target_temp):
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)


def _write_temporary(directory: Path, prefix: str, content: bytes, mode: int) -> Path:
    descriptor, name = tempfile.mkstemp(prefix=prefix, suffix=".tmp", dir=directory)
    temporary_path = Path(name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary_path, mode)
        return temporary_path
    except Exception:
        temporary_path.unlink(missing_ok=True)
        raise


def _fsync_directory(directory: Path) -> None:
    descriptor = os.open(directory, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
