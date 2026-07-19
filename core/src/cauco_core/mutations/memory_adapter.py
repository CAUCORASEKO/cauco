import hashlib
from datetime import UTC, datetime
from time import monotonic

from cauco_tools import ToolExecutionError, ToolExecutionRequest, ToolExecutionResult

from cauco_core.memory_writing.analyzer import MemoryWriteProposalError
from cauco_core.memory_writing.applier import (
    DuplicateMemoryContentError,
    MemoryWriteApplicationError,
    MemoryWriteProposalApplier,
)
from cauco_core.memory_writing.models import MemoryWriteOperation, MemoryWriteRequest
from cauco_core.memory_writing.proposal_builder import MemoryWriteProposalBuilder
from cauco_core.memory_writing.store import (
    MemoryWriteProposalStore,
    ProposalNotFoundError,
    ProposalStoreError,
)


class CoreMemoryMutationAdapter:
    tool_id = "memory"
    operations = frozenset({"create_proposal", "confirm_proposal"})

    def __init__(
        self,
        builder: MemoryWriteProposalBuilder,
        store: MemoryWriteProposalStore,
        applier: MemoryWriteProposalApplier,
    ) -> None:
        self.builder = builder
        self.store = store
        self.applier = applier

    def execute(self, request: ToolExecutionRequest) -> ToolExecutionResult:
        started_at = datetime.now(tz=UTC)
        started = monotonic()
        try:
            if request.operation_id == "create_proposal":
                data, performed = self._create(request)
                output = "Controlled memory proposal created; no Markdown was written."
            elif request.operation_id == "confirm_proposal":
                data, performed = self._confirm(request)
                output = (
                    "Memory proposal applied and verified."
                    if performed
                    else "Duplicate memory content was prevented; no Markdown was changed."
                )
            else:
                raise ToolExecutionError("unsupported_operation", "Memory mutation is unsupported.")
        except ToolExecutionError:
            raise
        except ProposalStoreError as error:
            raise ToolExecutionError("proposal_conflict", str(error)) from error
        except (MemoryWriteProposalError, MemoryWriteApplicationError) as error:
            raise ToolExecutionError("memory_mutation_failed", str(error)) from error
        completed_at = datetime.now(tz=UTC)
        return ToolExecutionResult(
            tool_id="memory",
            operation_id=request.operation_id,
            success=True,
            started_at=started_at,
            completed_at=completed_at,
            duration_ms=max(0, round((monotonic() - started) * 1000)),
            output=output,
            structured_data=data,
            mutation_performed=performed,
        )

    def _create(self, request: ToolExecutionRequest) -> tuple[dict[str, object], bool]:
        proposal_type = request.arguments.get("proposal_type")
        content = request.arguments.get("content")
        expected_proposal_id = request.arguments.get("expected_proposal_id")
        if (
            not isinstance(proposal_type, str)
            or not isinstance(content, str)
            or not isinstance(expected_proposal_id, str)
        ):
            raise ToolExecutionError(
                "invalid_arguments", "Typed memory proposal input is required."
            )
        try:
            operation = MemoryWriteOperation(proposal_type)
        except ValueError as error:
            raise ToolExecutionError(
                "invalid_arguments", "Memory proposal type is not allowed."
            ) from error
        proposal = self.builder.build(MemoryWriteRequest(instruction=content, operation=operation))
        if proposal.proposal_id != expected_proposal_id:
            raise ToolExecutionError(
                "stale_before_state",
                "The deterministic memory proposal changed after preview.",
            )
        duplicate = False
        try:
            self.store.get(proposal.proposal_id)
            duplicate = True
        except ProposalNotFoundError:
            pass
        stored = self.store.put(proposal)
        return (
            {
                "proposal_id": proposal.proposal_id,
                "proposal_type": proposal.operation.value,
                "destination": proposal.target_file,
                "target_section": proposal.target_section,
                "normalized_content": proposal.normalized_content,
                "preview": proposal.markdown_preview,
                "expires_at": stored.expires_at.isoformat(),
                "duplicate_prevented": duplicate,
                "memory_refreshed": False,
                "mutation_performed": not duplicate,
                "execution_performed": True,
            },
            not duplicate,
        )

    def _confirm(self, request: ToolExecutionRequest) -> tuple[dict[str, object], bool]:
        proposal_id = request.arguments.get("proposal_id")
        expected = request.arguments.get("expected_before_digest")
        expected_after = request.arguments.get("expected_after_digest")
        if (
            not isinstance(proposal_id, str)
            or not isinstance(expected, str)
            or not isinstance(expected_after, str)
        ):
            raise ToolExecutionError(
                "invalid_arguments", "Typed memory confirmation input is required."
            )
        stored = self.store.get_pending(proposal_id)
        target = self.applier._resolve_registered_target(stored.proposal)
        path = self.applier.memory_engine.memory_service.resolve_approved_write_target(
            target.relative_path
        )
        if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise ToolExecutionError(
                "stale_before_state", "The memory target changed after preview creation."
            )
        try:
            result = self.applier.apply(proposal_id)
        except DuplicateMemoryContentError:
            return (
                {
                    "proposal_id": proposal_id,
                    "destination": stored.proposal.target_file,
                    "duplicate_prevented": True,
                    "memory_refreshed": False,
                    "backup_created": False,
                    "verification_passed": True,
                    "mutation_performed": False,
                    "execution_performed": True,
                },
                False,
            )
        after = path.read_bytes()
        after_digest = hashlib.sha256(after).hexdigest()
        if after_digest != expected_after:
            raise ToolExecutionError("verification_failed", "Post-write verification failed.")
        return (
            {
                "proposal_id": proposal_id,
                "destination": result.target_file,
                "target_section": result.target_section,
                "memory_refreshed": result.memory_refreshed,
                "duplicate_prevented": False,
                "backup_created": True,
                "after_digest": after_digest,
                "verification_passed": True,
                "mutation_performed": True,
                "execution_performed": True,
            },
            True,
        )
