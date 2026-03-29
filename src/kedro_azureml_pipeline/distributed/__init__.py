"""Distributed training support for Azure ML."""

from .config import DistributedNodeConfig
from .decorators import distributed_job

__all__ = [
    "DistributedNodeConfig",
    "distributed_job",
]
