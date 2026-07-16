from datetime import UTC, datetime

import pytest

from cauco_scheduler import Job, JobKind, JobStatus, SchedulerRegistry
from cauco_scheduler.models import WEEKLY_RECAP_EXAMPLE


def test_registry_supports_one_time_and_recurring_jobs() -> None:
    registry = SchedulerRegistry()
    registry.register(
        Job(
            job_id="launch",
            name="Launch reminder",
            kind=JobKind.ONE_TIME,
            run_at=datetime(2030, 1, 1, tzinfo=UTC),
        )
    )
    registry.register(WEEKLY_RECAP_EXAMPLE)
    assert len(registry) == 2
    assert WEEKLY_RECAP_EXAMPLE.status is JobStatus.INACTIVE


def test_registry_rejects_duplicate_job_ids() -> None:
    registry = SchedulerRegistry()
    registry.register(WEEKLY_RECAP_EXAMPLE)
    with pytest.raises(ValueError, match="already registered"):
        registry.register(WEEKLY_RECAP_EXAMPLE)


def test_job_schedule_validation() -> None:
    with pytest.raises(ValueError, match="require run_at"):
        Job(job_id="invalid", name="Invalid", kind=JobKind.ONE_TIME)
    with pytest.raises(ValueError, match="require a recurrence"):
        Job(job_id="invalid-recurring", name="Invalid", kind=JobKind.RECURRING)
