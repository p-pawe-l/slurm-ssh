"""
Submitting Slurm jobs to an HPC cluster over SSH.

    config/    - reading and validating the YAML config
    job/       - HPCJob dataclass and batch script generation
    transport/ - SSH connection to the remote host
"""

import sys

from .config import InvalidConfigError, read_config


def main() -> None:
    """Entry point of the hpc-con command."""
    if len(sys.argv) != 2:
        sys.exit("usage: hpc-con <config.yaml>")
    try:
        print(read_config(sys.argv[1]))
    except (InvalidConfigError, OSError) as error:
        sys.exit(str(error))
