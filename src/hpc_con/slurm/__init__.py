"""
Slurm operations on the remote HPC cluster, the public API of hpc-con.

Only Slurm operations are exposed (submit, status, cancel, fetch output),
there is no function that runs an arbitrary command on the remote machine.

    cluster.py - SlurmCluster (submit, status, cancel, fetch_output)
"""

from .cluster import SlurmCluster

__all__ = ["SlurmCluster"]
