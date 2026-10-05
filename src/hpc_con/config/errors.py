"""
Errors reported while reading the YAML config.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class ConfigError:
    """Single problem found in the config, e.g. path="job.nodes"."""

    path: str
    message: str

    def __str__(self) -> str:
        return f"{self.path}: {self.message}"


class InvalidConfigError(Exception):
    """Raised when the config can't be used - carries all found problems."""

    def __init__(self, errors: list[ConfigError], source: str | None = None) -> None:
        self.errors = errors
        header = f"Invalid config {source!r}" if source else "Invalid config"
        details = "\n  - ".join(str(error) for error in errors)
        super().__init__(f"{header}:\n  - {details}")
