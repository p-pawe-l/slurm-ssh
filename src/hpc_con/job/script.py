"""
Generation of the Slurm batch script from a template.
"""

import shlex
from functools import cache
from importlib.resources import files
from string import Template

from .model import HPCJob
from .validation import JobValidationError, validate_job

TEMPLATE_DIRECTORY: str = "templates"
TEMPLATE_FILE: str = "slurm_job.txt"
ENCODING_TYPE: str = "utf-8"


@cache
# Loading Template(path.read_text(encoding=ENCDOING_TYPE)) into
# cache so next _load_template just reads it from cache instead
# of calling this function
def _load_template() -> Template:
    """Reads the batch scsript template shipped in the templates/ directory."""
    # files(__packages__) -> should return "src/hpc_con/job" :)
    path = files(__package__) / TEMPLATE_DIRECTORY / TEMPLATE_FILE
    return Template(path.read_text(encoding=ENCODING_TYPE))


def _create_options_for_sbtach_script_from_job(
    job: HPCJob,
) -> list[tuple[str, str | int | None]]:
    """
    Converts HPCJob into itterable list with tuples.
    Used to construct #SBATCH string for script.
    """
    return [
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


def _construct_sbatch_header(job: HPCJob) -> str:
    # Should look something like this as a string
    # #SBATCH --job-name=your_job-name
    # ...
    # #SBTACH --time=01:00:00
    # ...
    options: list[tuple[str, str | int | None]] = (
        _create_options_for_sbtach_script_from_job(job)
    )
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


def render_script(job: HPCJob, debug: bool) -> str:
    """Validates the job and returns the generated Slurm batch script."""
    errors = validate_job(job)
    if errors:
        raise JobValidationError(errors)

    return _load_template().substitute(
        sbatch_header=_construct_sbatch_header(job),
        setup=_setup(job),
        commands="\n".join(job.commands),
        debug=int(debug),
    )
