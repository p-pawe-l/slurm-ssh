"""
Structural validation of the loaded config: sections, keys and value types.

Values of the job (allowed characters, formats) are checked later
by hpc_con.job.validate_job - here we only make sure the data has the
right shape to build the dataclasses.
"""

import os
from difflib import get_close_matches
from typing import Any

from .consts import ENV_VALUE_TYPES, SECTIONS, STRING_LISTS, FieldSpec
from .errors import ConfigError


def _is_type(value: Any, types: tuple[type, ...]) -> bool:
    # bool is a subclass of int in Python - "nodes: true" must not pass as int
    if isinstance(value, bool) and bool not in types:
        return False
    return isinstance(value, types)


def _type_names(types: tuple[type, ...]) -> str:
    names = {str: "string", int: "integer", list: "list", dict: "mapping"}
    return " or ".join(names.get(t, t.__name__) for t in types)


def _unknown_key(path: str, key: Any, allowed: dict[str, Any]) -> ConfigError:
    message = "unknown key"
    suggestion = get_close_matches(str(key), allowed, n=1)
    if suggestion:
        message += f", did you mean {suggestion[0]!r}?"
    return ConfigError(f"{path}.{key}", message)


def _check_value(path: str, key: str, value: Any) -> list[ConfigError]:
    """Extra checks of the content of a single (correctly typed) value."""
    errors: list[ConfigError] = []
    if key in STRING_LISTS:
        errors += [
            ConfigError(f"{path}.{key}[{i}]", "must be a string")
            for i, item in enumerate(value)
            if not isinstance(item, str)
        ]
    if key == "env":
        for env_key, env_value in value.items():
            if not isinstance(env_key, str):
                errors.append(
                    ConfigError(f"{path}.env", f"key {env_key!r} must be a string")
                )
            elif not _is_type(env_value, ENV_VALUE_TYPES):
                errors.append(
                    ConfigError(f"{path}.env.{env_key}", "must be a string or number")
                )
    if key == "key_file" and not os.path.isfile(os.path.expanduser(value)):
        errors.append(ConfigError(f"{path}.{key}", f"file not found: {value}"))
    return errors


def _check_section(
    path: str, section: Any, schema: dict[str, FieldSpec]
) -> list[ConfigError]:
    if not isinstance(section, dict):
        return [ConfigError(path, "must be a mapping")]

    errors = [_unknown_key(path, key, schema) for key in section if key not in schema]
    for key, (types, required) in schema.items():
        if key not in section:
            if required:
                errors.append(ConfigError(f"{path}.{key}", "missing required key"))
            continue

        value = section[key]
        if _is_type(value, types):
            errors += _check_value(path, key, value)
        elif key == "time" and isinstance(value, int):
            # YAML reads unquoted 01:00:00 as a number (3600)
            errors.append(
                ConfigError(f"{path}.time", 'put the time in quotes, e.g. "01:00:00"')
            )
        else:
            expected, got = _type_names(types), type(value).__name__
            errors.append(
                ConfigError(f"{path}.{key}", f"expected {expected}, got {got}")
            )
    return errors


def validate_config(config: Any) -> list[ConfigError]:
    """
    Validates loaded config. Returns list of found errors in the config,
    empty list means the config can be parsed.
    """
    if not isinstance(config, dict):
        return [ConfigError("<root>", "config must be a mapping with sections")]

    errors = [
        _unknown_key("<root>", key, SECTIONS) for key in config if key not in SECTIONS
    ]
    for name, schema in SECTIONS.items():
        if name not in config:
            errors.append(ConfigError(name, "missing required section"))
        else:
            errors += _check_section(name, config[name], schema)
    return errors
