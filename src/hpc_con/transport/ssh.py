import subprocess as sp

from ..config import ConnectionConfig
from .utils import build_ssh_base, execute_local_cmd, execute_remote_cmd


class SSH_RemoteHost:
    def __init__(self, connection: ConnectionConfig, verbose: bool = False) -> None:
        self.connection: ConnectionConfig = connection
        self.ssh_base: list[str] = build_ssh_base(self.connection)
        self.target: str = (
            f"{self.connection.user}@{self.connection.host}"
            if self.connection.user
            else self.connection.host
        )
        self.verbose: bool = verbose

    def _verbose_start(self, connecting_result: sp.CompletedProcess[str]) -> None:
        print("Connecting to", self.target, "...")
        if connecting_result.returncode != 0:
            print(
                "Failed to connect to",
                self.target,
                "with error:",
                connecting_result.stderr,
            )
            raise ConnectionError(
                f"Failed to connect to {self.target} with error: {connecting_result.stderr}"
            )
        else:
            print("Connected to", self.target, "successfully.")

    def _verbose_end(self, disconnecting_result: sp.CompletedProcess[str]) -> None:
        print("Disconnecting from", self.target, "...")
        if disconnecting_result.returncode != 0:
            print(
                "Failed to disconnect from",
                self.target,
                "with error:",
                disconnecting_result.stderr,
            )
            raise ConnectionError(
                f"Failed to disconnect from {self.target} with error: {disconnecting_result.stderr}"
            )
        else:
            print("Disconnected from", self.target, "successfully.")

    def run(self, argv: list[str]) -> str:
        """Run a command on the remote host"""
        return execute_remote_cmd(self.ssh_base, argv)

    def put_file(self, local_path: str, remote_path: str) -> str:
        """Copies a file from local machine to remote one"""
        return execute_local_cmd(["scp", local_path, self.target + ":" + remote_path])

    def fetch_file(self, remote_path: str, local_path: str) -> str:
        """Copies a file from remote machine to local one"""
        return execute_local_cmd(["scp", self.target + ":" + remote_path, local_path])

    def __enter__(self) -> "SSH_RemoteHost":
        result: sp.CompletedProcess[str] = sp.run(
            self.ssh_base[:1]
            + ["-MNf", "-o", "ControlPersist=yes"]
            + self.ssh_base[1:],
            check=True,
        )
        if self.verbose:
            self._verbose_start(result)
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        result: sp.CompletedProcess[str] = sp.run(
            self.ssh_base[:1] + ["-o", "exit"] + self.ssh_base[1:], capture_output=True
        )
        if self.verbose:
            self._verbose_end(result)
