import shlex
import subprocess as sp
import typing as typ

from pydantic import BaseModel, StrictInt
from ..config import ConnectionConfig


class CommandExecutionResult(BaseModel):
    """
    Presents what sp.run(...) returns
    """

    result_stdout: str
    result_stderr: str
    result_returncode: StrictInt
    result_args: typ.Any


def execute_local_cmd(
    argv: list[str], **kwargs: dict[typ.Any]
) -> CommandExecutionResult:
    """Execute a command on the local machine"""
    result: sp.CompletedProcess[str] = sp.run(
        argv, capture_output=True, text=True, check=True, **kwargs
    )
    return CommandExecutionResult(
        result_stdout=result.stdout,
        result_stderr=result.stderr,
        result_returncode=result.returncode,
        result_args=result.args,
    )
