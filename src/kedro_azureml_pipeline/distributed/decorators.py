"""Decorators for marking Kedro nodes as distributed jobs."""

from functools import wraps

from kedro_azureml_pipeline.constants import DISTRIBUTED_CONFIG_FIELD
from kedro_azureml_pipeline.distributed.config import DistributedNodeConfig, Framework


def distributed_job(framework: Framework, num_nodes: str | int, **kwargs):
    """Mark a Kedro node function for distributed execution.

    Parameters
    ----------
    framework : Framework
        Distributed framework (PyTorch, TensorFlow, or MPI).
    num_nodes : str or int
        Number of compute nodes, or a ``params:`` reference.
    **kwargs
        Extra fields forwarded to ``DistributedNodeConfig``.

    Returns
    -------
    callable
        Decorator that attaches a ``DistributedNodeConfig`` to the
        wrapped function.

    See Also
    --------
    [DistributedNodeConfig][kedro_azureml_pipeline.distributed.config.DistributedNodeConfig] : Config attached by this decorator.
    [Framework][kedro_azureml_pipeline.distributed.config.Framework] : Supported frameworks.
    [AzureMLPipelineGenerator][kedro_azureml_pipeline.generator.AzureMLPipelineGenerator] : Reads the attached config.
    """

    def _decorator(func):
        """Attach distributed config to *func*."""
        config = DistributedNodeConfig(framework, num_nodes, **kwargs)
        setattr(
            func,
            DISTRIBUTED_CONFIG_FIELD,
            config,
        )

        @wraps(func)
        def wrapper(*args, **kws):
            """Forward call to the original function."""
            return func(*args, **kws)

        return wrapper

    return _decorator
