"""
Parsed config - plain data, no logic besides readable printing.
"""

from dataclasses import dataclass

from ..formatting import format_fields
from ..job import HPCJob


@dataclass(frozen=True, slots=True, kw_only=True)
class ConnectionConfig:
    host: str
    user: str | None = None
    port: int | None = None
    key_file: str | None = None

    def __str__(self) -> str:
        """Readable multi-line summary, unset fields fall back to ssh defaults."""
        return format_fields(
            "Connection",
            [
                ("host", self.host),
                ("user", self.user),
                ("port", self.port),
                ("key_file", self.key_file),
            ],
            missing="(ssh default)",
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class HPC_ConConfig:
    connection: ConnectionConfig
    job: HPCJob

    def __str__(self) -> str:
        """Readable summary of the connection and the job, one block each."""
        return f"{self.connection}\n\n{self.job}"
