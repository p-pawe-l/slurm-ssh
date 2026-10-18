import typing as typ
import subprocess as sp
import pathlib as ph

from ..config import ConnectionConfig
from functools import cache
from .utils import (
    execute_local_cmd,
    CommandExecutionResult,
)

# pre requirements
# Check whether ssh is installed <- if not, propose for user to install it, list a command for installing ssh and enabling it
# Check whether ssh daemon in running <- if not, propose for user to realod it, list a command for reloading ssh
# Before connecting show user set commands and options for ssh connection and ask whether they are correct <- just to be sure

SSH_OPTS: list[str] = [
    "-o",
    "ControlMaster=auto",
    "-o",
    "ControlPath=~/.ssh/cm-%C",
    "-o",
    "ControlPersist=10m",
    "-o",
    "BatchMode=yes",
]


@cache
def build_ssh_base(config: ConnectionConfig) -> list[str]:
    """
    ssh argv up to including the target, without remote command.
    """
    args: list[str] = ["ssh", *SSH_OPTS]
    if config.port:
        args += ["-p", str(config.port)]
    if config.key_file:
        args += ["-i", config.key_file]
    target: str = f"{config.user}@{config.host}"
    return args + ["--", target]


class SSHConnection:
    def __init__(self, config: ConnectionConfig, verbose: bool = False) -> None:
        self._config: ConnectionConfig = config
        self.verbose: bool = verbose
        self._ssh_base_args: list[str] = build_ssh_base(config)
        self.is_active: bool = False

    def connect(self) -> CommandExecutionResult:
        """
        Connects you machine via ssh with other machine.
        """
        result = execute_local_cmd(self._ssh_base_args)
        if result.result_returncode is 0:
            self.is_active = True
        return result

    def disconnect(self) -> CommandExecutionResult:
        if self.is_active is False:
            return

    def __run_cmd(
        self, argv: list[str], **kwargs: dict[str, typ.Any]
    ) -> CommandExecutionResult:
        """
        Runs provided command in argv form (splitted collection of keywords for command)
        """
        result: sp.CompletedProcess[str] = sp.run(
            argv, text=True, check=True, capture_output=True, **kwargs
        )
        return CommandExecutionResult(
            result_stdout=result.stdout,
            result_stderr=result.stderr,
            result_returncode=result.returncode,
            result_args=result.args,
        )

    def __copy_files(self, files: list[ph.Path]) -> list[CommandExecutionResult]:
        """
        Copy files from local machine to remote machine connected via ssh
        """
        results: list[CommandExecutionResult] = []
        for file in files:
            args: list[str] = [
                "scp",
                str(file.absolute()),
                f"{self.config.user}@{self.config.host}:{str(file)}",
            ]
            results.append(self.__run_cmd(args))
        return results

    def __fetch_files(self, files: list[ph.Path]) -> None:
        """
        Fetches files from remote machine and copy them into local machine via ssh
        """
        results: list[CommandExecutionResult] = []
        for file in files:
            args: list[str] = [
                "scp",
                f"{self.config.user}@{self.config.host}:{str(file)}",
                str(file.absolute()),
            ]
            results.append(self.__run_cmd(args))
        return results

    def __execute_remote_cmd(
        self, argv: list[str], **kwargs: dict[str, typ.Any]
    ) -> typ.Optional[CommandExecutionResult]:
        """
        Executes command specified in argv on remote mahcine connected via ssh
        """
        if self.is_active is False:
            return None
        ssh_base_argv: list[str] = self._ssh_base_args + argv
        return self.__run_cmd(ssh_base_argv, **kwargs)
