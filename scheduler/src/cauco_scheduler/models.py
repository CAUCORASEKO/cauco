from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


class JobStatus(StrEnum):
    INACTIVE = "inactive"
    READY = "ready"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class JobKind(StrEnum):
    ONE_TIME = "one_time"
    RECURRING = "recurring"


@dataclass(frozen=True, slots=True)
class Job:
    job_id: str
    name: str
    kind: JobKind
    status: JobStatus = JobStatus.INACTIVE
    run_at: datetime | None = None
    recurrence: str | None = None

    def __post_init__(self) -> None:
        if not self.job_id.strip():
            raise ValueError("Job ID cannot be empty.")
        if self.kind is JobKind.ONE_TIME and self.run_at is None:
            raise ValueError("One-time jobs require run_at.")
        if self.kind is JobKind.RECURRING and not self.recurrence:
            raise ValueError("Recurring jobs require a recurrence description.")
        if self.kind is JobKind.ONE_TIME and self.recurrence is not None:
            raise ValueError("One-time jobs cannot define recurrence.")


WEEKLY_RECAP_EXAMPLE = Job(
    job_id="weekly-recap",
    name="Weekly recap",
    kind=JobKind.RECURRING,
    status=JobStatus.INACTIVE,
    recurrence="Every Friday at 16:00 local time",
)
