"""
Parsed config - plain data, no logic.
"""

from dataclasses import dataclass

from ..job import HPCJob


@dataclass(frozen=True, slots=True, kw_only=True)
class ConnectionConfig:
    host: str
    user: str | None = None
    port: int | None = None
    key_file: str | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class HPC_ConConfig:
    connection: ConnectionConfig
    job: HPCJob
