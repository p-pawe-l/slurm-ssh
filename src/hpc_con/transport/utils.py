import shlex
import shutil
import subprocess as sp
import sys
import typing as typ
from functools import cache

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
def _build_ssh_base(config: ConnectionConfig) -> list[str]:
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


class SSHSetupError(Exception):
    """Raised when the local ssh setup is missing or rejected by the user."""


SSH_INSTALL_HINTS: dict[str, str] = {
    "linux": (
        "Debian/Ubuntu: sudo apt install openssh-client openssh-server"
        " && sudo systemctl enable --now ssh\n"
        "Fedora/RHEL:   sudo dnf install openssh-clients openssh-server"
        " && sudo systemctl enable --now sshd"
    ),
    "darwin": (
        "ssh ships with macOS, enable Remote Login with:"
        " sudo systemsetup -setremotelogin on"
    ),
}

SSH_RELOAD_HINTS: dict[str, str] = {
    "linux": "sudo systemctl restart sshd  (Debian/Ubuntu: sudo systemctl restart ssh)",
    "darwin": "sudo launchctl kickstart -k system/com.openssh.sshd",
}

# argv that exits 0 when the ssh daemon is up, tried in order
SSH_DAEMON_CHECKS: dict[str, list[list[str]]] = {
    "linux": [
        ["systemctl", "is-active", "--quiet", "sshd"],
        ["systemctl", "is-active", "--quiet", "ssh"],
    ],
    "darwin": [["launchctl", "print", "system/com.openssh.sshd"]],
}


def _platform_hint(hints: dict[str, str]) -> str:
    """Hint for the current platform, falls back to a generic message."""
    return hints.get(sys.platform, "see your system's OpenSSH documentation")


def _check_if_ssh_installed() -> None:
    """Raise SSHSetupError with an install command when ssh is not on PATH."""
    if shutil.which("ssh") is None:
        raise SSHSetupError(
            "ssh client not found on PATH. Install and enable it with:\n"
            + _platform_hint(SSH_INSTALL_HINTS)
        )


def _check_if_ssh_daemon_is_running() -> None:
    """Raise SSHSetupError with a reload command when the ssh daemon is down."""
    for argv in SSH_DAEMON_CHECKS.get(sys.platform, []):
        try:
            execute_local_cmd(argv)
        except (sp.CalledProcessError, FileNotFoundError):
            continue
        return
    raise SSHSetupError(
        "ssh daemon is not running. Reload it with:\n"
        + _platform_hint(SSH_RELOAD_HINTS)
    )


def _show_ssh_setup(config: ConnectionConfig, ssh_argv: list[str]) -> None:
    """
    Print the connection settings and the ssh command, ask the user to confirm.
    Raises SSHSetupError when the user does not answer yes.
    """
    print(config)
    print(f"ssh command: {shlex.join(ssh_argv)}")
    answer: str = input("Are these settings correct? [y/N] ").strip().lower()
    if answer not in ("y", "yes"):
        raise SSHSetupError("ssh setup rejected by the user")
