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


def _load_raw_config(yaml_filename: str) -> dict[str, Any]:
    """
    Loads raw YAML config from given filename. Raises InvalidConfigError
    when the file is not valid YAML.

    Returns a dict with the source filename when the file is empty,
    or a dict with the loaded config otherwise.
    """
    with open(yaml_filename, encoding="utf-8") as file_handle:
        try:
            config: dict[str, Any] | None = yaml.safe_load(file_handle)
            if not config: config = {} # This means that config was loaded successfully but is empty
            config["yaml_config_filename"] = yaml_filename
            return config
        except yaml.YAMLError as error:
            raise InvalidConfigError(
                [ConfigError("<yaml>", str(error))], source=yaml_filename
            ) from error


def _parse_config(config: dict[str, Any]) -> HPC_ConConfig:
    """
    Parses config dictionary into HPC_ConConfig dataclass.
    Expects a config that passed validate_config.
    """
    connection_dict: dict[str, Any] = dict(config["connection"])
    job_dict: dict[str, Any] = dict(config["job"])
    if "key_file" in connection_dict:
        connection_dict["key_file"] = os.path.expanduser(connection_dict["key_file"])
    if "mem" in job_dict:
        job_dict["mem"] = str(job_dict["mem"])
    if "env" in job_dict:
        job_dict["env"] = {key: str(value) for key, value in job_dict["env"].items()}

    return HPC_ConConfig(
        connection=ConnectionConfig(**connection_dict),
        job=HPCJob(**job_dict),
    )


def read_config(yaml_filename: str) -> HPC_ConConfig:
    """
    Loads, validates and parses the config file in one step.
    Raises InvalidConfigError with all found problems.
    """
    raw_config_dict: dict[str, Any] = _load_raw_config(yaml_filename)
    errors: list[ConfigError] = validate_config(raw_config_dict)
    if errors:
        raise InvalidConfigError(errors, source=raw_config_dict["yaml_config_filename"])
    config: HPC_ConConfig = _parse_config(raw_config_dict)
    job_errors = [ConfigError("job", message) for message in validate_job(config.job)]
    if job_errors:
        raise InvalidConfigError(job_errors, source=raw_config_dict["yaml_config_filename"])

    return config
