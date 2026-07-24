from cauco_core.learning.models import (
    ExperienceOutcome,
    ExperienceRecord,
    LessonCandidate,
    LessonCategory,
)
from cauco_core.learning.store import ExperienceStore
from cauco_core.verification.models import VerificationOutcome
from cauco_core.verification.store import VerificationStore


class ExperienceConsolidationService:
    METHOD = "deterministic_verification_consolidation_v1"

    def __init__(
        self, *, verification_store: VerificationStore, experience_store: ExperienceStore
    ) -> None:
        self.verification_store = verification_store
        self.experience_store = experience_store

    def consolidate(self, verification_id: str) -> ExperienceRecord:
        verification = self.verification_store.get(verification_id)
        candidates: list[LessonCandidate] = []
        rules = (
            (
                "A persistent mutation was reported without explicit post-action verification "
                "evidence.",
                LessonCategory.VERIFICATION,
                "Plans that can mutate persistent state should include an explicit post-action "
                "verification criterion.",
                0.95,
            ),
            (
                "No explicit success criterion or independent verification evidence is available.",
                LessonCategory.VERIFICATION,
                "Plans should define an explicit success criterion or independent verification "
                "evidence before execution.",
                0.93,
            ),
            (
                "Relevant verification output may be unavailable.",
                LessonCategory.VERIFICATION,
                "Verification output must preserve the evidence required to evaluate the approved "
                "success criteria.",
                0.92,
            ),
            (
                "No structured tool result is available.",
                LessonCategory.EXECUTION,
                "Executed operations should return structured results that can be independently "
                "verified.",
                0.94,
            ),
            (
                "The approved operation was not performed.",
                LessonCategory.EXECUTION,
                "A plan cannot be considered complete when an approved operation was not actually "
                "performed.",
                0.98,
            ),
        )
        for step in verification.step_results:
            for observation in step.unresolved_conditions:
                for needle, category, lesson, confidence in rules:
                    if needle in observation:
                        candidates.append(
                            LessonCandidate(
                                category,
                                observation,
                                lesson,
                                confidence,
                                True,
                                step.tool_id,
                                step.operation_id,
                                step.step_index,
                            )
                        )
            for observation in step.deviations:
                if "Tool result identity does not match the approved step." in observation:
                    candidates.append(
                        LessonCandidate(
                            LessonCategory.TOOL_RELIABILITY,
                            observation,
                            "Execution results must preserve the approved tool and operation "
                            "identity "
                            "before they can be trusted.",
                            0.99,
                            True,
                            step.tool_id,
                            step.operation_id,
                            step.step_index,
                        )
                    )
                elif "Post-action verification explicitly failed." in observation:
                    candidates.append(
                        LessonCandidate(
                            LessonCategory.VERIFICATION,
                            observation,
                            "A completed operation must not be treated as successful when its "
                            "post-action "
                            "verification fails.",
                            0.99,
                            True,
                            step.tool_id,
                            step.operation_id,
                            step.step_index,
                        )
                    )
                elif observation.strip():
                    candidates.append(
                        LessonCandidate(
                            LessonCategory.TOOL_RELIABILITY,
                            observation,
                            "Future plans using this tool-operation pair should account for the "
                            "observed "
                            "execution failure.",
                            0.80,
                            True,
                            step.tool_id,
                            step.operation_id,
                            step.step_index,
                        )
                    )
        unique: list[LessonCandidate] = []
        seen: set[tuple[str, str]] = set()
        for candidate in candidates:
            key = (candidate.observation, candidate.lesson)
            if key not in seen:
                seen.add(key)
                unique.append(candidate)
        outcome = {
            VerificationOutcome.SUCCEEDED: (
                ExperienceOutcome.SUCCESS,
                "All approved execution steps were successfully verified.",
            ),
            VerificationOutcome.PARTIAL_SUCCESS: (
                ExperienceOutcome.PARTIAL,
                "The execution produced mixed verification results and requires review before "
                "completion.",
            ),
            VerificationOutcome.FAILED: (
                ExperienceOutcome.FAILURE,
                "The execution failed verification and should not be treated as successfully "
                "completed.",
            ),
            VerificationOutcome.INSUFFICIENT_EVIDENCE: (
                ExperienceOutcome.INCONCLUSIVE,
                "The execution could not be conclusively verified from the available evidence.",
            ),
        }[verification.outcome]
        return self.experience_store.create(
            verification_id=verification.verification_id,
            execution_id=verification.execution_id,
            review_id=verification.review_id,
            snapshot_digest=verification.snapshot_digest,
            outcome=outcome[0],
            summary=outcome[1],
            lesson_candidates=tuple(unique),
            recommendation=verification.recommendation.value,
            method=self.METHOD,
        )
