"""
Validation of job values before they are placed in the batch script.

Every value is matched against a strict pattern (no whitespace, no newlines,
no shell metacharacters), so it cannot inject extra lines or commands.
"""

import re

from .model import HPCJob

NAME_RE = re.compile(r"^[A-Za-z0-9_.-]{1,64}$")
TIME_RE = re.compile(r"^(\d+-)?\d{1,3}(:\d{2}){0,2}$")  # MM, HH:MM:SS, D-HH:MM...
MEM_RE = re.compile(r"^\d+[KMGT]?$")
MODULE_RE = re.compile(r"^[A-Za-z0-9_.+/-]+$")
# %j, %x are Slurm placeholders; no "~" because #SBATCH lines don't expand it
PATH_RE = re.compile(r"^[A-Za-z0-9_./%-]+$")
ENV_KEY_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


class JobValidationError(ValueError):
    """Raised when a job contains values that are not allowed in the script."""

    def __init__(self, errors: list[str]) -> None:
        self.errors = errors
        super().__init__("Invalid job:\n  - " + "\n  - ".join(errors))


def _check_patterns(job: HPCJob) -> list[str]:
    checks: list[tuple[str, str | None, re.Pattern[str]]] = [
        ("name", job.name, NAME_RE),
        ("partition", job.partition, NAME_RE),
        ("account", job.account, NAME_RE),
        ("time", job.time, TIME_RE),
        ("mem", job.mem, MEM_RE),
        ("workdir", job.workdir, PATH_RE),
        ("output", job.output, PATH_RE),
        ("error", job.error, PATH_RE),
    ]
    checks += [("module", module, MODULE_RE) for module in job.modules]
    checks += [("env key", key, ENV_KEY_RE) for key in job.env]

    return [
        f"{label}: invalid value {value!r}"
        for label, value, pattern in checks
        if value is not None and not pattern.fullmatch(value)
    ]


def _check_numbers(job: HPCJob) -> list[str]:
    limits = [
        ("nodes", job.nodes, 1),
        ("ntasks", job.ntasks, 1),
        ("cpus_per_task", job.cpus_per_task, 1),
        ("gpus", job.gpus, 0),
    ]
    return [
        f"{label}: must be an integer >= {minimum}"
        for label, number, minimum in limits
        if not isinstance(number, int) or number < minimum
    ]


def validate_job(job: HPCJob) -> list[str]:
    """Returns list of found errors, empty list means the job is valid."""
    errors = _check_patterns(job) + _check_numbers(job)
    if not job.commands:
        errors.append("commands: at least one command is required")
    return errors
