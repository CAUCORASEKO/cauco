import difflib
import hashlib
import json
import secrets
from dataclasses import asdict
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any

from cauco_agents import (
    CalendarCreateEventInput,
    EmailDraftInput,
    FilesystemWriteTextInput,
    GitAddInput,
    GitCommitInput,
    GitPushInput,
    MemoryConfirmProposalInput,
    MemoryCreateProposalInput,
)
from cauco_tools import (
    ToolAdapterRegistry,
    ToolExecutionError,
    ToolExecutionRequest,
    ToolRegistry,
)
from cauco_tools.adapters import (
    FilesystemTextMutationAdapter,
    GitAddAdapter,
    GitCommitAdapter,
    GitPushAdapter,
)

from cauco_core.agents.review_store import (
    AgentPlanReviewStore,
    PlanReviewIntegrityError,
    PlanReviewNotFoundError,
)
from cauco_core.connectors.apple_calendar.tool_adapter import CalendarToolRuntimeAdapter
from cauco_core.connectors.apple_mail.tool_adapter import EmailToolRuntimeAdapter
from cauco_core.execution.models import (
    ExecutionConflictError,
    ExecutionForbiddenError,
    ExecutionNotFoundError,
    ExecutionValidationError,
    StepExecutionStatus,
)
from cauco_core.execution.service import ExecutionService
from cauco_core.execution.store import ExecutionStore
from cauco_core.memory_writing.analyzer import MemoryWriteProposalError
from cauco_core.memory_writing.applier import (
    DuplicateMemoryContentError,
    MemoryWriteApplicationError,
    insert_under_heading,
)
from cauco_core.memory_writing.models import MemoryWriteOperation, MemoryWriteRequest
from cauco_core.memory_writing.proposal_builder import MemoryWriteProposalBuilder
from cauco_core.memory_writing.store import (
    MemoryWriteProposalStore,
    ProposalNotFoundError,
    ProposalStoreError,
)
from cauco_core.mutations.models import (
    MutationConflictError,
    MutationForbiddenError,
    MutationNotFoundError,
    MutationPreview,
    MutationPreviewStatus,
    MutationValidationError,
)
from cauco_core.mutations.store import MutationPreviewStore

PHRASES = {
    ("memory", "create_proposal"): "APPLY MEMORY PROPOSAL",
    ("memory", "confirm_proposal"): "CONFIRM MEMORY WRITE",
    ("filesystem", "write_text_file"): "WRITE WORKSPACE FILE",
    ("git", "add"): "STAGE APPROVED FILES",
    ("git", "commit"): "CREATE APPROVED COMMIT",
    ("git", "push"): "PUSH APPROVED COMMIT",
    ("calendar", "create_event"): "CREATE CALENDAR EVENT",
    ("email", "draft"): "PREPARE EMAIL DRAFT",
}
DIFF_LIMIT = 20_000


class MutationService:
    def __init__(
        self,
        execution_service: ExecutionService,
        execution_store: ExecutionStore,
        review_store: AgentPlanReviewStore,
        tool_registry: ToolRegistry,
        adapter_registry: ToolAdapterRegistry,
        preview_store: MutationPreviewStore,
        proposal_builder: MemoryWriteProposalBuilder,
        proposal_store: MemoryWriteProposalStore,
    ) -> None:
        self.execution_service = execution_service
        self.execution_store = execution_store
        self.review_store = review_store
        self.tool_registry = tool_registry
        self.adapter_registry = adapter_registry
        self.preview_store = preview_store
        self.proposal_builder = proposal_builder
        self.proposal_store = proposal_store

    def create_preview(self, execution_id: str, step_index: int) -> MutationPreview:
        record, review, step, plan_step = self._bound_step(execution_id, step_index)
        self._event(record.execution_id, step, "mutation_preview_requested", "accepted")
        reference = plan_step.tool_reference
        assert reference is not None
        key = (reference.tool_id, reference.operation_id)
        if key == ("git", "add"):
            self._event(record.execution_id, step, "git_staging_preview_requested", "accepted")
        if key == ("git", "commit"):
            self._event(record.execution_id, step, "commit_preview_requested", "accepted")
        if key == ("git", "push"):
            self._event(record.execution_id, step, "push_preview_requested", "accepted")
        if key not in PHRASES:
            self._event(record.execution_id, step, "preview_rejected", "rejected")
            raise MutationConflictError("The approved step is not an enabled mutation.")
        validation = self.tool_registry.validate(*key)
        if not (
            validation.valid
            and validation.runtime_execution_allowed
            and validation.preview_required
            and self.adapter_registry.exists(*key)
        ):
            self._event(record.execution_id, step, "preview_rejected", "rejected")
            raise MutationConflictError("The approved mutation is not runtime-enabled.")
        try:
            fields = self._preview_fields(plan_step.operation_input, *key)
            if key == ("git", "add"):
                self._event(record.execution_id, step, "repository_validation_passed", "success")
                self._event(record.execution_id, step, "path_validation_passed", "success")
            if key == ("git", "commit"):
                self._event(record.execution_id, step, "repository_validation_passed", "success")
                self._event(record.execution_id, step, "staged_tree_captured", "success")
                self._event(record.execution_id, step, "identity_validation_passed", "success")
            if key == ("git", "push"):
                self._event(record.execution_id, step, "repository_validation_passed", "success")
                self._event(record.execution_id, step, "remote_state_discovered", "success")
                self._event(record.execution_id, step, "fast_forward_verified", "success")
            created_at = self.preview_store.clock()
            expires_at = created_at + self.preview_store.ttl
            phrase = PHRASES[key]
            digest = preview_digest(
                execution_id=execution_id,
                review_id=review.review_id,
                step_index=step_index,
                tool_id=key[0],
                operation_id=key[1],
                expires_at=expires_at,
                confirmation_phrase_id=phrase,
                **fields,
            )
            preview = self.preview_store.create(
                execution_id=execution_id,
                review_id=review.review_id,
                step_index=step_index,
                tool_id=key[0],
                operation_id=key[1],
                preview_digest=digest,
                confirmation_phrase=phrase,
                created_at=created_at,
                expires_at=expires_at,
                **fields,
            )
        except ToolExecutionError as error:
            if key == ("git", "add"):
                validation_event = {
                    "sensitive_path": "sensitive_path_rejected",
                    "ignored_target": "ignored_path_rejected",
                    "binary_target": "binary_path_rejected",
                    "oversized_target": "oversized_path_rejected",
                    "partial_staging": "partial_staging_rejected",
                    "blocked_git_state": "blocked_git_operation_state",
                    "unmerged_state": "blocked_git_operation_state",
                }.get(error.code, "path_validation_failed")
                self._event(record.execution_id, step, validation_event, "rejected")
            self._event(record.execution_id, step, "preview_rejected", "rejected")
            if error.forbidden:
                raise MutationForbiddenError(error.safe_message) from error
            if error.code in {
                "target_exists",
                "target_missing",
                "partial_staging",
                "blocked_git_state",
                "unmerged_state",
                "no_changes",
                "repository_mismatch",
                "not_git_repository",
                "index_locked",
                "no_staged_changes",
                "staged_paths_mismatch",
                "identity_missing",
                "detached_head",
                "stale_state",
                "missing_remote",
                "remote_state_mismatch",
                "branch_mismatch",
                "local_commit_mismatch",
                "staged_index",
                "non_fast_forward",
                "outgoing_commit_count",
                "already_published",
            }:
                raise MutationConflictError(error.safe_message) from error
            raise MutationValidationError(error.safe_message) from error
        except (MutationConflictError, MutationForbiddenError, MutationValidationError):
            self._event(record.execution_id, step, "preview_rejected", "rejected")
            raise
        except ProposalStoreError as error:
            self._event(record.execution_id, step, "preview_rejected", "rejected")
            raise MutationConflictError(str(error)) from error
        except (MemoryWriteProposalError, MemoryWriteApplicationError) as error:
            self._event(record.execution_id, step, "preview_rejected", "rejected")
            raise MutationValidationError(str(error)) from error
        self._event(record.execution_id, step, "preview_created", "success")
        return preview

    def get_preview(self, execution_id: str, step_index: int) -> MutationPreview:
        _, _, step, _ = self._bound_step(execution_id, step_index)
        preview = self.preview_store.active(execution_id, step_index)
        if preview.status is MutationPreviewStatus.EXPIRED:
            self._event(execution_id, step, "preview_expired", "expired")
            raise MutationConflictError("Mutation preview has expired.")
        return preview

    def cancel_preview(self, execution_id: str, step_index: int) -> MutationPreview:
        _, _, step, _ = self._bound_step(execution_id, step_index)
        preview = self.preview_store.cancel(execution_id, step_index)
        self._event(execution_id, step, "preview_cancelled", "cancelled")
        return preview

    def confirm(
        self,
        execution_id: str,
        step_index: int,
        *,
        preview_id: str,
        preview_digest_value: str,
        confirmation_phrase: str,
    ):
        _, _, step, _ = self._bound_step(execution_id, step_index)
        self._event(execution_id, step, "confirmation_requested", "accepted")
        preview = self.preview_store.get(preview_id)
        if preview.execution_id != execution_id or preview.step_index != step_index:
            self._reject(execution_id, step, "confirmation_rejected")
            raise MutationConflictError("Mutation preview does not belong to this execution step.")
        if preview.status is MutationPreviewStatus.EXPIRED:
            self._reject(execution_id, step, "preview_expired")
            raise MutationConflictError("Mutation preview has expired.")
        if preview.status is not MutationPreviewStatus.PENDING_CONFIRMATION:
            self._reject(execution_id, step, "confirmation_rejected")
            raise MutationConflictError(f"Mutation preview is already {preview.status.value}.")
        if not secrets.compare_digest(preview.preview_digest, preview_digest_value):
            self._reject(execution_id, step, "digest_mismatch")
            raise MutationConflictError("Mutation preview digest does not match.")
        if confirmation_phrase != preview.confirmation_phrase:
            self._reject(execution_id, step, "confirmation_phrase_mismatch")
            raise MutationValidationError(
                "The operation-specific confirmation phrase does not match."
            )
        try:
            self._verify_before_state(preview)
            self.preview_store.claim(preview_id, execution_id, step_index)
        except ProposalStoreError as error:
            self._reject(execution_id, step, "confirmation_rejected")
            raise MutationConflictError(str(error)) from error
        self.execution_store.start_step(execution_id, step_index)
        self._event(execution_id, step, "adapter_started", "accepted")
        adapter = self.adapter_registry.get(preview.tool_id, preview.operation_id)
        request = ToolExecutionRequest(
            tool_id=preview.tool_id,
            operation_id=preview.operation_id,
            arguments=preview.normalized_arguments,
        )
        try:
            result = adapter.execute(request)
        except ToolExecutionError as error:
            if preview.tool_id == "git" and preview.operation_id == "add":
                self._event(execution_id, step, "git_add_failed", "failed")
                if getattr(error, "recovery_attempted", False):
                    self._event(execution_id, step, "recovery_attempted", "accepted")
                    self._event(
                        execution_id,
                        step,
                        "recovery_succeeded"
                        if getattr(error, "recovery_succeeded", False)
                        else "recovery_failed",
                        "success" if getattr(error, "recovery_succeeded", False) else "failed",
                    )
            result = self.execution_service._failed_result(
                execution_id, step_index, preview.tool_id, preview.operation_id, error
            )
            finished = self.execution_store.finish_step(
                execution_id, step_index, result=result, error=error.safe_message, performed=True
            )
            self._event(execution_id, step, "mutation_failed", "failed")
            if error.code == "verification_failed":
                self._event(execution_id, step, "verification_failed", "failed")
            self.preview_store.consume(preview_id)
            self._event(execution_id, step, "preview_consumed", "consumed")
            return finished
        except Exception:
            error = ToolExecutionError("mutation_failed", "The mutation failed safely.")
            result = self.execution_service._failed_result(
                execution_id, step_index, preview.tool_id, preview.operation_id, error
            )
            finished = self.execution_store.finish_step(
                execution_id, step_index, result=result, error=error.safe_message, performed=True
            )
            self._event(execution_id, step, "mutation_failed", "failed")
            self.preview_store.consume(preview_id)
            self._event(execution_id, step, "preview_consumed", "consumed")
            return finished
        finished = self.execution_store.finish_step(
            execution_id, step_index, result=result, error=result.error_message, performed=True
        )
        data = result.structured_data
        if data.get("backup_created"):
            self._event(execution_id, step, "index_backup_created", "success")
        if data.get("fixed_git_add_invoked"):
            self._event(execution_id, step, "fixed_git_add_invoked", "success")
            self._event(execution_id, step, "post_status_captured", "success")
        if data.get("fixed_git_commit_invoked"):
            self._event(execution_id, step, "fixed_git_commit_invoked", "success")
            self._event(execution_id, step, "commit_verification_passed", "success")
        if data.get("fixed_git_push_invoked"):
            self._event(execution_id, step, "fixed_git_push_invoked", "success")
            self._event(execution_id, step, "remote_verification_passed", "success")
        if data.get("verification_passed"):
            self._event(execution_id, step, "verification_passed", "success")
        if data.get("memory_refreshed"):
            self._event(execution_id, step, "memory_engine_refreshed", "success")
        if data.get("duplicate_prevented"):
            self._event(execution_id, step, "duplicate_prevented", "bounded")
        self._event(execution_id, step, "mutation_completed", "success")
        self.preview_store.consume(preview_id)
        self._event(execution_id, step, "preview_consumed", "consumed")
        return finished

    def _bound_step(self, execution_id: str, step_index: int):
        try:
            record = self.execution_store.get(execution_id)
            review = self.review_store.get(record.review_id)
            self.execution_service._validate_review(review)
        except (ExecutionNotFoundError, PlanReviewNotFoundError) as error:
            raise MutationNotFoundError(str(error)) from error
        except (ExecutionConflictError, PlanReviewIntegrityError) as error:
            raise MutationConflictError(str(error)) from error
        if review.snapshot_digest != record.snapshot_digest:
            raise MutationConflictError("Snapshot digest verification failed.")
        step = next((item for item in record.step_records if item.step_index == step_index), None)
        plan_step = next((item for item in review.plan.steps if item.order == step_index), None)
        if step is None or plan_step is None:
            raise MutationNotFoundError("Execution step not found.")
        if step.status is not StepExecutionStatus.PENDING:
            raise MutationConflictError(f"Step is already {step.status.value}.")
        return record, review, step, plan_step

    def _preview_fields(self, operation_input: object, tool_id: str, operation_id: str):
        if isinstance(operation_input, EmailDraftInput):
            adapter = self.adapter_registry.get(tool_id, operation_id)
            if not isinstance(adapter, EmailToolRuntimeAdapter):
                raise MutationConflictError("Email mutation adapter is unavailable.")
            arguments = asdict(operation_input)
            adapter.preflight(ToolExecutionRequest(tool_id, operation_id, arguments))
            request_id = f"email_draft_{secrets.token_hex(12)}"
            normalized_arguments = {
                **arguments,
                "request_id": request_id,
            }
            return {
                "target": operation_input.recipient,
                "normalized_arguments": normalized_arguments,
                "before_state": {"draft_created": False},
                "proposed_after_state": {
                    "recipient": operation_input.recipient,
                    "subject": operation_input.subject,
                    "body": operation_input.body,
                    "draft_created": True,
                    "sent": False,
                },
                "diff_preview": email_draft_preview(operation_input),
            }

        if isinstance(operation_input, CalendarCreateEventInput):
            adapter = self.adapter_registry.get(tool_id, operation_id)
            if not isinstance(adapter, CalendarToolRuntimeAdapter):
                raise MutationConflictError("Calendar mutation adapter is unavailable.")
            arguments = asdict(operation_input)
            adapter.preflight(ToolExecutionRequest(tool_id, operation_id, arguments))
            request_id = f"calendar_create_{secrets.token_hex(12)}"
            normalized_arguments = {**arguments, "request_id": request_id}
            return {
                "target": operation_input.calendar_reference,
                "normalized_arguments": normalized_arguments,
                "before_state": {"event_created": False},
                "proposed_after_state": {
                    "title": operation_input.title,
                    "start": operation_input.start,
                    "end": operation_input.end,
                    "all_day": operation_input.all_day,
                    "calendar_reference": operation_input.calendar_reference,
                    "location": operation_input.location,
                    "notes": operation_input.notes,
                },
                "diff_preview": calendar_event_preview(operation_input),
            }
        if isinstance(operation_input, FilesystemWriteTextInput):
            policy = self.execution_service.workspace_policy
            if policy is None:
                raise MutationConflictError("No execution workspace is configured.")
            try:
                policy_target = policy.validate_write_target(operation_input.relative_path)
            except ExecutionForbiddenError as error:
                raise MutationForbiddenError(str(error)) from error
            except ExecutionValidationError as error:
                raise MutationValidationError(str(error)) from error
            adapter = self.adapter_registry.get(tool_id, operation_id)
            if not isinstance(adapter, FilesystemTextMutationAdapter):
                raise MutationConflictError("Filesystem mutation adapter is unavailable.")
            if len(operation_input.content) > adapter.max_content_chars:
                raise MutationValidationError("Text content exceeds the safe write limit.")
            target, relative = adapter.resolve_target(operation_input.relative_path)
            if relative != policy_target:
                raise MutationForbiddenError("Workspace target validation did not agree.")
            exists = target.exists()
            if operation_input.overwrite_policy == "create_only" and exists:
                raise ToolExecutionError("target_exists", "The create-only target already exists.")
            if operation_input.overwrite_policy == "replace_existing" and not exists:
                raise ToolExecutionError("target_missing", "The replacement target does not exist.")
            before_bytes = target.read_bytes() if exists else None
            try:
                before_text = before_bytes.decode("utf-8") if before_bytes is not None else ""
            except UnicodeDecodeError as error:
                raise ToolExecutionError(
                    "invalid_content", "Existing target is not UTF-8 text."
                ) from error
            before = sha(before_bytes) if before_bytes is not None else None
            after = sha(operation_input.content.encode("utf-8"))
            return {
                "target": relative,
                "normalized_arguments": {
                    **asdict(operation_input),
                    "expected_before_digest": before,
                },
                "before_state": {"exists": exists, "digest": before},
                "proposed_after_state": {
                    "exists": True,
                    "digest": after,
                    "characters": len(operation_input.content),
                    "overwrite_policy": operation_input.overwrite_policy,
                    "backup_on_replace": exists,
                },
                "diff_preview": bounded_diff(before_text, operation_input.content, relative),
            }
        if isinstance(operation_input, GitAddInput):
            policy = self.execution_service.workspace_policy
            if policy is None:
                raise MutationConflictError("No execution workspace is configured.")
            adapter = self.adapter_registry.get(tool_id, operation_id)
            if not isinstance(adapter, GitAddAdapter) or adapter.workspace != policy.root:
                raise MutationConflictError("The configured Git staging adapter is unavailable.")
            captured = adapter.inspect(operation_input.paths)
            return {
                "target": None,
                "normalized_arguments": {
                    "paths": captured["paths"],
                    "expected_index_digest": captured["before_index_digest"],
                    "expected_worktree_digest": captured["before_worktree_state_digest"],
                    "expected_staged_state_digest": captured["before_staged_state_digest"],
                },
                "before_state": {
                    "repository_label": captured["repository_label"],
                    "repository_id": captured["repository_id"],
                    "index_digest": captured["before_index_digest"],
                    "staged_state_digest": captured["before_staged_state_digest"],
                    "worktree_state_digest": captured["before_worktree_state_digest"],
                    "already_staged_paths": captured["before_staged_paths"],
                },
                "proposed_after_state": {
                    "repository_label": captured["repository_label"],
                    "paths": captured["paths"],
                    "path_count": captured["path_count"],
                    "path_states": captured["path_states"],
                    "warning": (
                        "This stages only the exact approved files and does not commit or push."
                    ),
                },
                "diff_preview": captured["diff_preview"],
            }
        if isinstance(operation_input, GitCommitInput):
            policy = self.execution_service.workspace_policy
            if policy is None:
                raise MutationConflictError("No execution workspace is configured.")
            adapter = self.adapter_registry.get(tool_id, operation_id)
            if not isinstance(adapter, GitCommitAdapter) or adapter.workspace != policy.root:
                raise MutationConflictError("The configured Git commit adapter is unavailable.")
            captured = adapter.inspect_commit(
                operation_input.message, operation_input.expected_staged_paths
            )
            return {
                "target": None,
                "normalized_arguments": {
                    "message": captured["message"],
                    "expected_staged_paths": captured["expected_staged_paths"],
                    "staged_tree_id": captured["staged_tree_id"],
                    "current_head_id": captured["current_head_id"],
                    "current_branch": captured["current_branch"],
                    "index_digest": captured["index_digest"],
                },
                "before_state": {
                    "repository_label": captured["repository_label"],
                    "repository_id": captured["repository_id"],
                    "current_head_id": captured["current_head_id"],
                    "current_branch": captured["current_branch"],
                    "staged_tree_id": captured["staged_tree_id"],
                    "index_digest": captured["index_digest"],
                    "author_name": captured["author_name"],
                    "author_email_masked": captured["author_email_masked"],
                },
                "proposed_after_state": {
                    "commit_message": captured["message"],
                    "expected_staged_paths": captured["expected_staged_paths"],
                    "actual_staged_paths": captured["actual_staged_paths"],
                    "staged_path_count": len(captured["actual_staged_paths"]),
                    "staged_tree_id": captured["staged_tree_id"],
                    "diff_stat": captured["diff_stat"],
                    "hooks_policy": "Local Git hooks may run during commit.",
                    "warning": "This creates one local commit. It does not stage files or push.",
                },
                "diff_preview": captured["diff_preview"],
            }
        if isinstance(operation_input, GitPushInput):
            policy = self.execution_service.workspace_policy
            if policy is None:
                raise MutationConflictError("No execution workspace is configured.")
            adapter = self.adapter_registry.get(tool_id, operation_id)
            if not isinstance(adapter, GitPushAdapter) or adapter.workspace != policy.root:
                raise MutationConflictError("The configured Git push adapter is unavailable.")
            captured = adapter.inspect_push(operation_input)
            return {
                "target": None,
                "normalized_arguments": {
                    "remote": operation_input.remote,
                    "local_branch": operation_input.local_branch,
                    "remote_branch": operation_input.remote_branch,
                    "expected_local_commit": operation_input.expected_local_commit,
                    "expected_remote_commit": operation_input.expected_remote_commit,
                    "local_tree_id": captured["local_tree_id"],
                    "outgoing_commits": captured["outgoing_commits"],
                    "index_digest": captured["index_digest"],
                    "remote_label": captured["remote_label"],
                },
                "before_state": {
                    "repository_label": captured["repository_label"],
                    "remote_label": captured["remote_label"],
                    "remote_name": captured["remote_name"],
                    "local_branch": captured["local_branch"],
                    "remote_branch": captured["remote_branch"],
                    "local_commit": captured["local_commit"],
                    "current_remote_commit": captured["current_remote_commit"],
                    "index_clean": captured["index_clean"],
                },
                "proposed_after_state": {
                    "outgoing_commits": captured["outgoing_commits"],
                    "outgoing_commit_count": captured["outgoing_commit_count"],
                    "commit_subject": captured["commit_subject"],
                    "changed_paths": captured["changed_paths"],
                    "fast_forward_verified": True,
                    "worktree_warning": "Unstaged worktree changes are left untouched.",
                    "warning": (
                        "This publishes one local commit without force, tags, "
                        "or additional branches."
                    ),
                },
                "diff_preview": "\n".join(captured["changed_paths"]),
            }
        if isinstance(operation_input, MemoryCreateProposalInput):
            proposal = self.proposal_builder.build(
                MemoryWriteRequest(
                    instruction=operation_input.content,
                    operation=MemoryWriteOperation(operation_input.proposal_type),
                )
            )
            return {
                "target": proposal.target_file,
                "normalized_arguments": {
                    **asdict(operation_input),
                    "expected_proposal_id": proposal.proposal_id,
                },
                "before_state": {"proposal_exists": self._proposal_exists(proposal.proposal_id)},
                "proposed_after_state": {
                    "proposal_id": proposal.proposal_id,
                    "proposal_type": proposal.operation.value,
                    "destination": proposal.target_file,
                    "target_section": proposal.target_section,
                    "normalized_content": proposal.normalized_content,
                },
                "diff_preview": proposal.markdown_preview[:DIFF_LIMIT],
            }
        if isinstance(operation_input, MemoryConfirmProposalInput):
            stored = self.proposal_store.get_pending(operation_input.proposal_id)
            proposal = stored.proposal
            matches = [
                item
                for item in self.proposal_builder.memory_engine.list_objects()
                if item.relative_path.casefold() == proposal.target_file.casefold()
            ]
            if len(matches) != 1:
                raise MutationValidationError("The approved memory target is unavailable.")
            memory_service = self.proposal_builder.memory_engine.memory_service
            target = memory_service.resolve_approved_write_target(matches[0].relative_path)
            before_bytes = target.read_bytes()
            before_text = before_bytes.decode("utf-8")
            try:
                after_text = insert_under_heading(
                    before_text, proposal.target_section, proposal.markdown_preview
                )
                duplicate = False
            except DuplicateMemoryContentError:
                after_text = before_text
                duplicate = True
            before = sha(before_bytes)
            return {
                "target": proposal.target_file,
                "normalized_arguments": {
                    "proposal_id": operation_input.proposal_id,
                    "expected_before_digest": before,
                    "expected_after_digest": sha(after_text.encode("utf-8")),
                },
                "before_state": {"digest": before, "proposal_state": stored.state.value},
                "proposed_after_state": {
                    "digest": sha(after_text.encode("utf-8")),
                    "proposal_id": proposal.proposal_id,
                    "destination": proposal.target_file,
                    "target_section": proposal.target_section,
                    "duplicate_prevented": duplicate,
                },
                "diff_preview": bounded_diff(before_text, after_text, proposal.target_file),
            }
        raise MutationValidationError("The approved mutation input is missing or invalid.")

    def _verify_before_state(self, preview: MutationPreview) -> None:
        if preview.tool_id == "email" and preview.operation_id == "draft":
            try:
                adapter = self.adapter_registry.get("email", "draft")
            except KeyError:
                self._stale(preview)
            if not isinstance(adapter, EmailToolRuntimeAdapter):
                self._stale(preview)
            try:
                adapter.preflight(
                    ToolExecutionRequest(
                        preview.tool_id,
                        preview.operation_id,
                        preview.normalized_arguments,
                    )
                )
            except ToolExecutionError:
                self._stale(preview)
            return

        if preview.tool_id == "calendar" and preview.operation_id == "create_event":
            try:
                adapter = self.adapter_registry.get("calendar", "create_event")
            except KeyError:
                self._stale(preview)
            if not isinstance(adapter, CalendarToolRuntimeAdapter):
                self._stale(preview)
            try:
                adapter.preflight(
                    ToolExecutionRequest(
                        preview.tool_id,
                        preview.operation_id,
                        preview.normalized_arguments,
                    )
                )
            except ToolExecutionError:
                self._stale(preview)
            return
        if preview.tool_id == "git" and preview.operation_id == "add":
            adapter = self.adapter_registry.get("git", "add")
            if not isinstance(adapter, GitAddAdapter):
                self._stale(preview)
            try:
                adapter.verify_preview(preview.normalized_arguments)
            except ToolExecutionError as error:
                event = "index_stale" if error.code == "index_stale" else "worktree_stale"
                step = next(
                    item
                    for item in self.execution_store.get(preview.execution_id).step_records
                    if item.step_index == preview.step_index
                )
                self._event(preview.execution_id, step, event, "rejected")
                self._stale(preview)
            return
        if preview.tool_id == "git" and preview.operation_id == "commit":
            adapter = self.adapter_registry.get("git", "commit")
            if not isinstance(adapter, GitCommitAdapter):
                self._stale(preview)
            try:
                adapter.verify_commit_preview(preview.normalized_arguments)
            except ToolExecutionError:
                step = next(
                    item
                    for item in self.execution_store.get(preview.execution_id).step_records
                    if item.step_index == preview.step_index
                )
                self._event(preview.execution_id, step, "commit_state_stale", "rejected")
                self._stale(preview)
            return
        if preview.tool_id == "git" and preview.operation_id == "push":
            adapter = self.adapter_registry.get("git", "push")
            if not isinstance(adapter, GitPushAdapter):
                self._stale(preview)
            try:
                adapter.verify_push_preview(preview.normalized_arguments)
            except ToolExecutionError:
                step = next(
                    item
                    for item in self.execution_store.get(preview.execution_id).step_records
                    if item.step_index == preview.step_index
                )
                self._event(preview.execution_id, step, "remote_state_stale", "rejected")
                self._stale(preview)
            return
        if preview.operation_id == "create_proposal":
            proposal_type = preview.normalized_arguments.get("proposal_type")
            content = preview.normalized_arguments.get("content")
            expected_id = preview.normalized_arguments.get("expected_proposal_id")
            if not all(isinstance(item, str) for item in (proposal_type, content, expected_id)):
                self._stale(preview)
            proposal = self.proposal_builder.build(
                MemoryWriteRequest(
                    instruction=content,
                    operation=MemoryWriteOperation(proposal_type),
                )
            )
            existed = preview.before_state.get("proposal_exists") is True
            if proposal.proposal_id != expected_id or self._proposal_exists(expected_id) != existed:
                self._stale(preview)
        expected = preview.before_state.get("digest")
        if expected is None and preview.tool_id == "filesystem":
            adapter = self.adapter_registry.get(preview.tool_id, preview.operation_id)
            assert isinstance(adapter, FilesystemTextMutationAdapter)
            try:
                target, _ = adapter.resolve_target(str(preview.target))
            except ToolExecutionError:
                self._stale(preview)
            if target.exists():
                self._stale(preview)
        elif isinstance(expected, str):
            if preview.tool_id == "filesystem":
                adapter = self.adapter_registry.get(preview.tool_id, preview.operation_id)
                assert isinstance(adapter, FilesystemTextMutationAdapter)
                try:
                    target, _ = adapter.resolve_target(str(preview.target))
                except ToolExecutionError:
                    self._stale(preview)
            else:
                matches = [
                    item
                    for item in self.proposal_builder.memory_engine.list_objects()
                    if item.relative_path.casefold() == str(preview.target).casefold()
                ]
                if len(matches) != 1:
                    self._stale(preview)
                memory_service = self.proposal_builder.memory_engine.memory_service
                target = memory_service.resolve_approved_write_target(matches[0].relative_path)
            if not target.exists() or sha(target.read_bytes()) != expected:
                self._stale(preview)
        if preview.operation_id == "confirm_proposal":
            proposal_id = preview.normalized_arguments.get("proposal_id")
            if not isinstance(proposal_id, str):
                self._stale(preview)
            self.proposal_store.get_pending(proposal_id)

    def _proposal_exists(self, proposal_id: str) -> bool:
        try:
            self.proposal_store.get(proposal_id)
        except ProposalNotFoundError:
            return False
        return True

    def _stale(self, preview: MutationPreview) -> None:
        step = next(
            item
            for item in self.execution_store.get(preview.execution_id).step_records
            if item.step_index == preview.step_index
        )
        self._event(preview.execution_id, step, "stale_before_state", "rejected")
        self.preview_store.cancel(preview.execution_id, preview.step_index)
        self._event(preview.execution_id, step, "preview_cancelled", "cancelled")
        raise MutationConflictError("Persistent state changed after preview creation.")

    def _reject(self, execution_id: str, step: object, event: str) -> None:
        self._event(execution_id, step, event, "rejected")

    def _event(self, execution_id: str, step: Any, event: str, outcome: str) -> None:
        self.execution_store.append_event(
            execution_id,
            event,
            outcome,
            event.replace("_", " ").capitalize() + ".",
            step_index=step.step_index,
            tool_id=step.tool_id,
            operation_id=step.operation_id,
        )


def sha(value: bytes | None) -> str:
    return hashlib.sha256(value or b"").hexdigest()


def bounded_diff(before: str, after: str, relative: str) -> str:
    value = "".join(
        difflib.unified_diff(
            before.splitlines(keepends=True),
            after.splitlines(keepends=True),
            fromfile=f"a/{relative}",
            tofile=f"b/{relative}",
        )
    )
    return value[:DIFF_LIMIT]


def email_draft_preview(value: EmailDraftInput) -> str:
    fields = (
        ("Recipient", value.recipient),
        ("Subject", value.subject),
        ("Body", value.body),
        ("Action", "create draft only"),
        ("Send", "no"),
    )
    return "\n".join(f"{label}: {content}" for label, content in fields)[:DIFF_LIMIT]


def calendar_event_preview(value: CalendarCreateEventInput) -> str:
    fields = (
        ("Title", value.title),
        ("Start", value.start),
        ("End", value.end),
        ("All day", "yes" if value.all_day else "no"),
        ("Calendar", value.calendar_reference or "default writable calendar"),
        ("Location", value.location or ""),
        ("Notes", value.notes or ""),
    )
    return "\n".join(f"{label}: {content}" for label, content in fields)[:DIFF_LIMIT]


def preview_digest(**fields: Any) -> str:
    def normalize(value: Any) -> Any:
        if isinstance(value, dict):
            return {key: normalize(item) for key, item in value.items()}
        if isinstance(value, (tuple, list)):
            return [normalize(item) for item in value]
        if isinstance(value, Enum):
            return value.value
        if isinstance(value, Path):
            return value.as_posix()
        if isinstance(value, datetime):
            return value.isoformat()
        return value

    canonical = json.dumps(
        normalize(fields), ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
