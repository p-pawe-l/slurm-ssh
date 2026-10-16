"""
Description of a single HPC job - plain data, no logic besides readable printing.
"""

from dataclasses import dataclass, field

from ..formatting import format_fields


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

    def __str__(self) -> str:
        """Readable multi-line summary, unset fields fall back to cluster defaults."""
        return format_fields(
            "Job",
            [
                ("name", self.name),
                ("commands", self.commands),
                ("partition", self.partition),
                ("account", self.account),
                ("time", self.time),
                ("nodes", self.nodes),
                ("ntasks", self.ntasks),
                ("cpus_per_task", self.cpus_per_task),
                ("mem", self.mem),
                ("gpus", self.gpus),
                ("modules", self.modules),
                ("env", self.env),
                ("workdir", self.workdir),
                ("output", self.output),
                ("error", self.error),
            ],
            missing="(cluster default)",
        )
