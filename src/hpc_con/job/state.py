"""
State of a submitted job as Slurm reports it (scontrol, or sacct once the job is gone).
"""

from enum import Enum

from pydantic import BaseModel, ConfigDict

# States in which the job can still change, every other state is final
ACTIVE_STATES = frozenset({"PENDING", "RUNNING", "COMPLETING", "SUSPENDED"})


class JobState(Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETING = "COMPLETING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    TIMEOUT = "TIMEOUT"
    OUT_OF_MEMORY = "OUT_OF_MEMORY"
    NODE_FAIL = "NODE_FAIL"
    PREEMPTED = "PREEMPTED"
    SUSPENDED = "SUSPENDED"
    UNKNOWN = "UNKNOWN"

    @classmethod
    def parse(cls, raw: str) -> "JobState":
        """'CANCELLED by 1234' -> CANCELLED, anything not recognised -> UNKNOWN."""
        words: list[str] = raw.split()
        return cls.__members__.get(words[0], cls.UNKNOWN) if words else cls.UNKNOWN

    @property
    def is_finished(self) -> bool:
        return self.value not in ACTIVE_STATES and self is not JobState.UNKNOWN


class JobInfo(BaseModel):
    """Snapshot of a Slurm job, fields Slurm did not report are None."""

    model_config = ConfigDict(frozen=True)

    job_id: int
    state: JobState
    name: str | None = None
    reason: str | None = None  # why the job is pending, e.g. "Resources"
    exit_code: str | None = None  # "exit status:signal", e.g. "0:0"
    run_time: str | None = None
    node_list: str | None = None
    stdout: str | None = None  # remote path of the output file
    stderr: str | None = None  # remote path of the error file

    @property
    def is_finished(self) -> bool:
        return self.state.is_finished
