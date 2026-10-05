"""
Reading and parsing YAML config file for HPC Connection.
"""

import os
from typing import Any

import yaml

from ..job import HPCJob, validate_job
from .errors import ConfigError, InvalidConfigError
from .model import ConnectionConfig, HPC_ConConfig
from .validation import validate_config


def load_config(yaml_filename: str) -> Any:
    """
    Loads raw config from given filename. Raises InvalidConfigError
    when the file is not valid YAML.
    """
    with open(yaml_filename, encoding="utf-8") as file_handle:
        try:
            config = yaml.safe_load(file_handle)
        except yaml.YAMLError as error:
            raise InvalidConfigError(
                [ConfigError("<yaml>", str(error))], source=yaml_filename
            ) from error
    # An empty file is loaded as None
    return {} if config is None else config


def parse_config(config: dict[str, Any]) -> HPC_ConConfig:
    """
    Parses config dictionary into HPC_ConConfig dataclass.
    Expects a config that passed validate_config.
    """
    connection = dict(config["connection"])
    if "key_file" in connection:
        connection["key_file"] = os.path.expanduser(connection["key_file"])

    job = dict(config["job"])
    if "mem" in job:
        job["mem"] = str(job["mem"])
    if "env" in job:
        job["env"] = {key: str(value) for key, value in job["env"].items()}

    return HPC_ConConfig(
        connection=ConnectionConfig(**connection),
        job=HPCJob(**job),
    )


def read_config(yaml_filename: str) -> HPC_ConConfig:
    """
    Loads, validates and parses the config file in one step.
    Raises InvalidConfigError with all found problems.
    """
    raw = load_config(yaml_filename)

    errors = validate_config(raw)
    if errors:
        raise InvalidConfigError(errors, source=yaml_filename)

    config = parse_config(raw)

    job_errors = [ConfigError("job", message) for message in validate_job(config.job)]
    if job_errors:
        raise InvalidConfigError(job_errors, source=yaml_filename)

    return config
