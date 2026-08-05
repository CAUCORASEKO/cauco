from contextlib import suppress

from cauco_agents import AgentPlanReviewStatus

from cauco_core.agents.review_store import AgentPlanReviewStore
from cauco_core.cognitive_cycle.models import CognitiveCycleSnapshot
from cauco_core.execution.models import ExecutionStatus
from cauco_core.execution.store import ExecutionStore
from cauco_core.learning.store import ExperienceNotFoundError, ExperienceStore
from cauco_core.memory_candidates.models import MemoryCandidateStatus
from cauco_core.memory_candidates.store import MemoryCandidateStore
from cauco_core.memory_writing.models import MemoryWriteProposalState
from cauco_core.memory_writing.store import MemoryWriteProposalStore
from cauco_core.verification.models import VerificationOutcome
from cauco_core.verification.store import VerificationNotFoundError, VerificationStore


class CognitiveCycleResolver:
    METHOD = "deterministic_cognitive_cycle_observer_v1"

    def __init__(
        self,
        review_store: AgentPlanReviewStore,
        execution_store: ExecutionStore,
        verification_store: VerificationStore,
        experience_store: ExperienceStore,
        candidate_store: MemoryCandidateStore,
        proposal_store: MemoryWriteProposalStore,
    ):
        self.review_store = review_store
        self.execution_store = execution_store
        self.verification_store = verification_store
        self.experience_store = experience_store
        self.candidate_store = candidate_store
        self.proposal_store = proposal_store

    def resolve(self, review_id: str) -> CognitiveCycleSnapshot:
        review = self.review_store.get(review_id)
        warnings: list[str] = []
        execution = self._one(
            self.execution_store.list(review_id=review_id, limit=100), warnings, "execution"
        )
        verification = None
        experience = None
        if execution:
            with suppress(VerificationNotFoundError):
                verification = self.verification_store.for_execution(execution.execution_id)
        if verification:
            with suppress(ExperienceNotFoundError):
                experience = self.experience_store.for_verification(verification.verification_id)
        for record, label in (
            (execution, "execution"),
            (verification, "verification"),
            (experience, "experience"),
        ):
            if record and (
                record.review_id != review_id or record.snapshot_digest != review.snapshot_digest
            ):
                warnings.append(f"{label} record does not match the review snapshot.")
        candidates = self.candidate_store.list(review_id=review_id, limit=100)
        proposals = self.proposal_store.list(source_type="memory_candidate", limit=100)
        proposals = tuple(
            p for p in proposals if p.proposal.source_id in {c.candidate_id for c in candidates}
        )
        cc = {s.value: sum(c.status is s for c in candidates) for s in MemoryCandidateStatus}
        pc = {s.value: sum(p.state is s for p in proposals) for s in MemoryWriteProposalState}
        ids = {
            "execution_id": execution.execution_id if execution else None,
            "verification_id": verification.verification_id if verification else None,
            "experience_id": experience.experience_id if experience else None,
            "candidate_ids": tuple(
                c.candidate_id for c in sorted(candidates, key=lambda c: c.candidate_id)
            ),
            "proposal_ids": tuple(
                p.proposal.proposal_id
                for p in sorted(proposals, key=lambda p: p.proposal.proposal_id)
            ),
        }
        stage, status, action, endpoint, human, terminal = self._stage(
            review_id, review.status, execution, verification, experience, candidates, proposals
        )
        if warnings:
            stage, status, action, endpoint, human, terminal = (
                "inconsistent",
                "inconsistent",
                None,
                None,
                False,
                False,
            )
        return CognitiveCycleSnapshot(
            review_id,
            stage,
            status,
            bool(stage == "inconsistent"),
            terminal,
            human,
            action,
            endpoint,
            ids,
            cc,
            pc,
            tuple(sorted(set(warnings))),
            (
                "Observation is bounded to 100 records per source and performs no lifecycle "
                "transition.",
            ),
            self.METHOD,
        )

    @staticmethod
    def _one(records, warnings, label):
        if len(records) > 1:
            warnings.append(f"Multiple {label} records exist for the review.")
        return (
            sorted(records, key=lambda r: getattr(r, "execution_id", getattr(r, "created_at", "")))[
                0
            ]
            if records
            else None
        )

    def _stage(self, review_id, rs, ex, ver, xp, cs, ps):
        if rs is AgentPlanReviewStatus.PENDING_REVIEW:
            return (
                "awaiting_plan_approval",
                "pending",
                "approve_or_reject_plan",
                f"/api/agents/plan-reviews/{review_id}",
                True,
                False,
            )
        if rs is not AgentPlanReviewStatus.APPROVED:
            return "completed", rs.value, None, None, False, True
        if not ex:
            return (
                "ready_for_execution",
                "ready",
                "create_execution",
                "/api/executions",
                False,
                False,
            )
        if ex.status in {ExecutionStatus.PENDING_EXECUTION, ExecutionStatus.RUNNING}:
            return (
                "execution_in_progress",
                ex.status.value,
                "continue_execution",
                f"/api/executions/{ex.execution_id}",
                False,
                False,
            )
        if ex.status is ExecutionStatus.FAILED:
            return "failed", "failed", None, None, False, True
        if not ver:
            return (
                "awaiting_verification",
                "awaiting_verification",
                "create_verification",
                "/api/verifications",
                False,
                False,
            )
        if ver.outcome in {VerificationOutcome.FAILED, VerificationOutcome.INSUFFICIENT_EVIDENCE}:
            return "failed", ver.outcome.value, None, None, False, True
        if not xp:
            return (
                "awaiting_experience_consolidation",
                "awaiting_experience",
                "consolidate_experience",
                "/api/experiences",
                False,
                False,
            )
        if not cs:
            return "completed", "completed", None, None, False, True
        if any(c.status is MemoryCandidateStatus.PENDING_REVIEW for c in cs):
            return (
                "awaiting_memory_candidate_review",
                "awaiting_human_action",
                "review_memory_candidate",
                "/api/memory-candidates",
                True,
                False,
            )
        approved = [c for c in cs if c.status is MemoryCandidateStatus.APPROVED]
        if approved and not any(p.state is MemoryWriteProposalState.APPLIED for p in ps):
            pending = next((p for p in ps if p.state is MemoryWriteProposalState.PENDING), None)
            return (
                "awaiting_memory_write_confirmation" if pending else "awaiting_candidate_promotion",
                "awaiting_human_action",
                "confirm_memory_write" if pending else "promote_candidate",
                f"/api/memory-writes/{pending.proposal.proposal_id}"
                if pending
                else "/api/memory-candidates",
                True,
                False,
            )
        return "learning_applied", "completed", None, None, False, True
