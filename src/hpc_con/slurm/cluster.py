import typing as typ
import pathlib as ph

from ..transport import SSHConnection, CommandExecutionResult
from ..job import render_script, HPCJob, JobInfo


class SlurmCluster:
    """Public API: Slurm operations only, no arbitrary commands"""

    def __init__(self, ssh_con: SSHConnection) -> None:
        self.ssh_active_con: SSHConnection | None = (
            ssh_con if ssh_con.is_active else None
        )

    def submit(
        self, job: HPCJob, debug: bool = False, filename: str | None = None
    ) -> int:
        """
        Renders script in string form from provided job and submits it.
        Used slurm commands:
        sbtach --parsable
        """
        job_script: str = render_script(job, debug, filename)
        remote_cmd: list[str] = ["sbatch --parsable"]
        self.ssh_active_con.__execute_remote_cmd(remote_cmd, input=job_script)

    def status(self, job_id: int) -> JobInfo:
        """
        Check status for you job.
        Used slurm commands:
        scontrol
        """
        remote_cmd: list[str] = [f"scontrol {job_id}"]
        self.ssh_active_con.__execute_remote_cmd(remote_cmd)

    def cancel(self, job_id: int) -> None:
        remote_cmd: list[str] = [f"scancel {job_id}"]
        self.ssh_active_con.__execute_remote_cmd(remote_cmd)

    def fetch_output(self, job_id: int, dest: ph.Path) -> ph.Path: ...
