"""Helpers for detecting distributed training environments."""

import json
import logging
import os

logger = logging.getLogger()


def is_distributed_master_node() -> bool:
    """Check whether this process is the master node.

    Inspects ``TF_CONFIG``, ``OMPI_COMM_WORLD_RANK``, and ``RANK``
    environment variables.

    Returns
    -------
    bool
        ``True`` if this process is rank 0 or the detection fails.

    See Also
    --------
    [is_distributed_environment][kedro_azureml_pipeline.distributed.utils.is_distributed_environment] : Detects distributed context.
    [DistributedNodeConfig][kedro_azureml_pipeline.distributed.config.DistributedNodeConfig] : Per-node distributed config.
    """
    is_rank_0 = True
    try:
        if "TF_CONFIG" in os.environ:
            # TensorFlow
            tf_config = json.loads(os.environ["TF_CONFIG"])
            worker_type = tf_config["task"]["type"].lower()
            is_rank_0 = (worker_type in {"chief", "master"}) or (
                worker_type == "worker" and tf_config["task"]["index"] == 0
            )
        else:
            # MPI + PyTorch
            for e in ("OMPI_COMM_WORLD_RANK", "RANK"):
                if e in os.environ:
                    is_rank_0 = int(os.environ[e]) == 0
                    break
    except (json.JSONDecodeError, KeyError, ValueError, TypeError):
        logger.error(
            "Could not parse environment variables related to distributed computing. "
            "Set appropriate values for one of: RANK, OMPI_COMM_WORLD_RANK or TF_CONFIG",
            exc_info=True,
        )
        logger.warning("Assuming this node is not a master node, due to error.")
        return False
    return is_rank_0


def is_distributed_environment() -> bool:
    """Check whether the process is running in a distributed context.

    Returns
    -------
    bool
        ``True`` if any distributed rank variable is set.

    See Also
    --------
    [is_distributed_master_node][kedro_azureml_pipeline.distributed.utils.is_distributed_master_node] : Checks master rank.
    [DistributedNodeConfig][kedro_azureml_pipeline.distributed.config.DistributedNodeConfig] : Per-node distributed config.
    """
    return any(e in os.environ for e in ("OMPI_COMM_WORLD_RANK", "RANK", "TF_CONFIG"))
