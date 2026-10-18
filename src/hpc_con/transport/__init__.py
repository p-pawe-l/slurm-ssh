"""
SSH transport to the remote HPC host.

    ssh.py   - SSHConnection (ssh argv built from ConnectionConfig, connect)
    utils.py - helpers for running local and remote commands, not exported
"""

from ._ssh import SSHConnection
from .utils import CommandExecutionResult

__all__ = ["CommandExecutionResult", "SSHConnection"]
