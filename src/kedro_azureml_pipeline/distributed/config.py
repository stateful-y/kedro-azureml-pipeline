"""Distributed training configuration models."""

import json
from dataclasses import asdict, dataclass
from enum import StrEnum


class Framework(StrEnum):
    """Supported distributed training frameworks."""

    PyTorch = "PyTorch"
    TensorFlow = "TensorFlow"
    MPI = "MPI"


@dataclass
class DistributedNodeConfig:
    """Configuration for a distributed training node.

    Parameters
    ----------
    framework : Framework
        Distributed training framework to use.
    num_nodes : str or int
        Number of compute nodes.
    processes_per_node : str, int, or None
        Number of processes to launch per node.

    See Also
    --------
    `kedro_azureml_pipeline.distributed.decorators.distributed_job` : Decorator that creates this config.
    `kedro_azureml_pipeline.generator.AzureMLPipelineGenerator` : Reads this config during generation.
    """

    framework: Framework
    num_nodes: str | int
    processes_per_node: str | int | None = None

    def __repr__(self):
        """Return a JSON string representation.

        Returns
        -------
        str
            JSON-serialized configuration.
        """
        return json.dumps(asdict(self))

    def __str__(self):
        """Return a JSON string representation.

        Returns
        -------
        str
            JSON-serialized configuration.
        """
        return self.__repr__()
