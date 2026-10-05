"""
Generation of the Slurm batch script from a template.
"""

import shlex
from functools import cache
from importlib.resources import files
from string import Template

from .model import HPCJob
from .validation import JobValidationError, validate_job

TEMPLATE_FILE = "slurm_job.txt"


@cache
def _load_template() -> Template:
    """Reads the batch script template shipped in the templates/ directory."""
    path = files(__package__) / "templates" / TEMPLATE_FILE
    return Template(path.read_text(encoding="utf-8"))


def _sbatch_header(job: HPCJob) -> str:
    options: list[tuple[str, str | int | None]] = [
        ("job-name", job.name),
        ("partition", job.partition),
        ("account", job.account),
        ("time", job.time),
        ("nodes", job.nodes),
        ("ntasks", job.ntasks),
        ("cpus-per-task", job.cpus_per_task),
        ("mem", job.mem),
        ("gpus", job.gpus or None),
        ("chdir", job.workdir),
        ("output", job.output),
        ("error", job.error),
    ]
    return "\n".join(
        f"#SBATCH --{option}={value}" for option, value in options if value
    )


def _setup(job: HPCJob) -> str:
    lines: list[str] = []
    if job.modules:
        lines.append("module purge")
        lines += [f"module load {shlex.quote(module)}" for module in job.modules]
    lines += [f"export {key}={shlex.quote(value)}" for key, value in job.env.items()]
    return "\n".join(lines) + "\n" if lines else ""


def render_script(job: HPCJob) -> str:
    """Validates the job and returns the generated Slurm batch script."""
    errors = validate_job(job)
    if errors:
        raise JobValidationError(errors)

    return _load_template().substitute(
        sbatch_header=_sbatch_header(job),
        setup=_setup(job),
        commands="\n".join(job.commands),
    )
