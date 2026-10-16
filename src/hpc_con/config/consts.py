"""
Schema of the config file: allowed sections, keys and their value types.
"""

from .types import FieldSpec

CONNECTION_SCHEMA: dict[str, FieldSpec] = {
    "host": ((str,), True),
    "user": ((str,), False),
    "port": ((int,), False),
    "key_file": ((str,), False),
}

JOB_SCHEMA: dict[str, FieldSpec] = {
    "name": ((str,), True),
    "commands": ((list,), True),
    "partition": ((str,), False),
    "account": ((str,), False),
    "time": ((str,), False),
    "nodes": ((int,), False),
    "ntasks": ((int,), False),
    "cpus_per_task": ((int,), False),
    "mem": ((str, int), False),
    "gpus": ((int,), False),
    "modules": ((list,), False),
    "env": ((dict,), False),
    "workdir": ((str,), False),
    "output": ((str,), False),
    "error": ((str,), False),
}

SECTIONS: dict[str, dict[str, FieldSpec] | FieldSpec] = {
    "connection": CONNECTION_SCHEMA,
    "job": JOB_SCHEMA,
}

# Lists whose items must all be strings
STRING_LISTS = {"commands", "modules"}
ENV_VALUE_TYPES = (str, int, float)
