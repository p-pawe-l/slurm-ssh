"""
Description of a single HPC job - plain data, no logic.
"""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class HPCJob:
    name: str
    commands: list[str]

    partition: str | None = None
    account: str | None = None
    time: str = "01:00:00"  # default time is 1 hour for given job
    nodes: int = 1
    ntasks: int = 1
    cpus_per_task: int = 1
    mem: str | None = None  # this is memory per cpu
    gpus: int = 0

    modules: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)

    workdir: str | None = None
    output: str = "%x-%j.out"
    error: str = "%x-%j.err"
