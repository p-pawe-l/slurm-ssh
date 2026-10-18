import pathlib as ph
import subprocess as sp
import typing as typ

from ..config import ConnectionConfig
from .utils import (
    CommandExecutionResult,
    _build_ssh_base,
    _check_if_ssh_daemon_is_running,
    _check_if_ssh_installed,
    _show_ssh_setup,
)


class SSHConnection:
    def __init__(self, config: ConnectionConfig, verbose: bool = False) -> None:
        self._config: ConnectionConfig = config
        self.verbose: bool = verbose
        self._ssh_base_args: list[str] = _build_ssh_base(config)
        self.is_active: bool = False

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

    def connect(self) -> CommandExecutionResult:
        """
        Connects you machine via ssh with other machine.
        """
        _check_if_ssh_installed()
        _check_if_ssh_daemon_is_running()
        _show_ssh_setup(self._config, self._ssh_base_args)

        result = self.__run_cmd(self._ssh_base_args)
        if result.result_returncode == 0:
            self.is_active = True
        return result

    def disconnect(self) -> CommandExecutionResult:
        if self.is_active is False:
            return

    def copy_files(self, files: list[ph.Path]) -> list[CommandExecutionResult]:
        """
        Copy files from local machine to remote machine connected via ssh
        """
        results: list[CommandExecutionResult] = []
        for file in files:
            args: list[str] = [
                "scp",
                str(file.absolute()),
                f"{self._config.user}@{self._config.host}:{str(file)}",
            ]
            results.append(self.__run_cmd(args))
        return results

    def fetch_files(self, files: list[ph.Path]) -> None:
        """
        Fetches files from remote machine and copy them into local machine via ssh
        """
        results: list[CommandExecutionResult] = []
        for file in files:
            args: list[str] = [
                "scp",
                f"{self._config.user}@{self._config.host}:{str(file)}",
                str(file.absolute()),
            ]
            results.append(self.__run_cmd(args))
        return results

    def __execute_remote_cmd(
        self, argv: list[str], **kwargs: dict[str, typ.Any]
    ) -> CommandExecutionResult | None:
        """
        Executes command specified in argv on remote mahcine connected via ssh
        """
        if self.is_active is False:
            return None
        ssh_base_argv: list[str] = self._ssh_base_args + argv
        return self.__run_cmd(ssh_base_argv, **kwargs)
