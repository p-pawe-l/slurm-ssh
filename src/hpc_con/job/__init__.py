"""
HPC job description and Slurm batch script generation.

    model.py      - HPCJob dataclass (what the job is)
    validation.py - checks that values are safe to put in the script
    script.py     - fills the batch script template
"""

from .model import HPCJob
from .script import render_script
from .validation import JobValidationError, validate_job

__all__ = ["HPCJob", "JobValidationError", "render_script", "validate_job"]
