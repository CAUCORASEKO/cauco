from datetime import UTC, datetime

import pytest
from cauco_tools import ToolExecutionResult

from cauco_core.execution.models import (
    AgentPlanStepExecutionRecord,
    StepExecutionStatus,
)
from cauco_core.verification import (
    VerificationConflictError,
    VerificationOutcome,
    VerificationStore,
)
from cauco_core.verification.service import VerificationService

NOW = datetime(2026, 7, 24, tzinfo=UTC)


def make_result(
    *,
    success: bool = True,
    structured_data: dict[str, object] | None = None,
    truncated: bool = False,
    mutation_performed: bool = False,
) -> ToolExecutionResult:
    return ToolExecutionResult(
        tool_id="filesystem",
        operation_id="write_text_file",
        success=success,
        started_at=NOW,
        completed_at=NOW,
        duration_ms=0,
        output="bounded result",
        structured_data=structured_data or {},
        error_code=None if success else "operation_failed",
        error_message=None if success else "Operation failed.",
        truncated=truncated,
        execution_performed=True,
        mutation_performed=mutation_performed,
    )


def make_step(
    result: ToolExecutionResult | None,
    *,
    performed: bool = True,
) -> AgentPlanStepExecutionRecord:
    return AgentPlanStepExecutionRecord(
        step_index=1,
        tool_id="filesystem",
        operation_id="write_text_file",
        target="notes.txt",
        status=(
            StepExecutionStatus.COMPLETED
            if result is not None and result.success
            else StepExecutionStatus.FAILED
        ),
        started_at=NOW,
        completed_at=NOW,
        result=result,
        execution_performed=performed,
    )


def service_without_stores() -> VerificationService:
    return object.__new__(VerificationService)


def test_explicit_post_action_verification_succeeds() -> None:
    service = service_without_stores()
    step = make_step(
        make_result(
            structured_data={"verification_passed": True},
            mutation_performed=True,
        )
    )

    result = service._verify_step(step)

    assert result.outcome is VerificationOutcome.SUCCEEDED
    assert not result.unresolved_conditions


def test_success_without_verification_is_insufficient() -> None:
    service = service_without_stores()
    step = make_step(make_result(mutation_performed=True))

    result = service._verify_step(step)

    assert result.outcome is VerificationOutcome.INSUFFICIENT_EVIDENCE
    assert result.unresolved_conditions


def test_explicit_verification_failure_fails() -> None:
    service = service_without_stores()
    step = make_step(
        make_result(
            structured_data={"verification_passed": False},
        )
    )

    result = service._verify_step(step)

    assert result.outcome is VerificationOutcome.FAILED
    assert result.deviations


def test_truncated_output_cannot_be_verified_successfully() -> None:
    service = service_without_stores()
    step = make_step(
        make_result(
            structured_data={"verification_passed": True},
            truncated=True,
        )
    )

    result = service._verify_step(step)

    assert result.outcome is VerificationOutcome.INSUFFICIENT_EVIDENCE


def test_failed_adapter_result_is_verification_failure() -> None:
    service = service_without_stores()
    step = make_step(make_result(success=False))

    result = service._verify_step(step)

    assert result.outcome is VerificationOutcome.FAILED
    assert result.deviations == ("operation_failed",)


def test_mixed_success_and_unknown_is_partial_success() -> None:
    service = service_without_stores()
    results = (
        service._verify_step(
            make_step(
                make_result(
                    structured_data={"verification_passed": True},
                )
            )
        ),
        service._verify_step(
            AgentPlanStepExecutionRecord(
                step_index=2,
                tool_id="filesystem",
                operation_id="write_text_file",
                target="other.txt",
                status=StepExecutionStatus.COMPLETED,
                started_at=NOW,
                completed_at=NOW,
                result=make_result(),
                execution_performed=True,
            )
        ),
    )

    assert service._overall_outcome(results) is VerificationOutcome.PARTIAL_SUCCESS


def test_store_allows_only_one_verification_per_execution() -> None:
    store = VerificationStore()
    step = service_without_stores()._verify_step(
        make_step(
            make_result(
                structured_data={"verification_passed": True},
            )
        )
    )
    execution_id = "exec_abcdefghijklmnopqrst"

    store.create(
        execution_id=execution_id,
        review_id="planrev_abcdefghijklmnopqrst",
        snapshot_digest="a" * 64,
        outcome=VerificationOutcome.SUCCEEDED,
        recommendation=(service_without_stores()._recommendation(VerificationOutcome.SUCCEEDED)),
        method=VerificationService.METHOD,
        step_results=(step,),
    )

    with pytest.raises(VerificationConflictError):
        store.create(
            execution_id=execution_id,
            review_id="planrev_abcdefghijklmnopqrst",
            snapshot_digest="a" * 64,
            outcome=VerificationOutcome.SUCCEEDED,
            recommendation=(
                service_without_stores()._recommendation(VerificationOutcome.SUCCEEDED)
            ),
            method=VerificationService.METHOD,
            step_results=(step,),
        )
