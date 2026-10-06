import subprocess as sp
import shlex

from ..config import ConnectionConfig


def execute_local_cmd(cmd: list[str]) -> str:
    """Execute a command on the local machine"""
    joined_cmd_str: str = shlex.join(cmd)
    result: sp.CompletedProcess[str] = sp.run(
        joined_cmd_str, capture_output=True, text=True, check=True
    )
    return result.stdout


def execute_remote_cmd(ssh_base: list[str], cmd: list[str]) -> str:
    """Execute a command on remote machine"""
    remote_cmd_lstr: list[str] = ssh_base + cmd
    return execute_local_cmd(remote_cmd_lstr)


def build_ssh_base(connection: ConnectionConfig) -> list[str]:
    """Build bash command for connecting to ssh"""
    args: list[str] = ["shh", "-o", "ControlPath=~/.ssh/cm-%C"]
    if connection.port:
        args += ["-p", str(connection.port)]
    if connection.key_file:
        args += ["-i", str(connection.key_file)]
    return args + [connection.target]
