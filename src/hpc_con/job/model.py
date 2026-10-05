"""
Description of a single HPC job - plain data, no logic.
"""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class HPCJob:
    name: str
    # Job payload - inserted into the script verbatim, trusted by design
    commands: list[str]

    # Resources
    partition: str | None = None
    account: str | None = None
    time: str = "01:00:00"
    nodes: int = 1
    ntasks: int = 1
    cpus_per_task: int = 1
    mem: str | None = None
    gpus: int = 0

    # Environment
    modules: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)

    # Files (%x = job name, %j = job id)
    workdir: str | None = None
    output: str = "%x-%j.out"
    error: str = "%x-%j.err"
