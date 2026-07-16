from cauco_scheduler.models import Job


class SchedulerRegistry:
    """Stores job definitions only; it does not execute or schedule them."""

    def __init__(self) -> None:
        self._jobs: dict[str, Job] = {}

    def register(self, job: Job) -> None:
        if job.job_id in self._jobs:
            raise ValueError(f"Job '{job.job_id}' is already registered.")
        self._jobs[job.job_id] = job

    def get(self, job_id: str) -> Job:
        try:
            return self._jobs[job_id]
        except KeyError as error:
            raise KeyError(f"Unknown job '{job_id}'.") from error

    def list_jobs(self) -> tuple[Job, ...]:
        return tuple(self._jobs.values())

    def __len__(self) -> int:
        return len(self._jobs)
