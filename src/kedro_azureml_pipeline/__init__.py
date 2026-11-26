"""Kedro AzureML Pipeline.

The public names are resolved lazily (PEP 562) rather than imported here. Importing
a leaf submodule such as :mod:`kedro_azureml_pipeline.distributed` must not pull in
``kedro.framework``: a project's logging handlers may import that submodule while
``kedro.framework.project`` is still initializing (it applies the logging config and
emits its first record before its own import completes), and an eager import of the
runner or the context manager from here would then hit a circular import. Accessing
``kedro_azureml_pipeline.AzurePipelinesRunner`` and the other names below still
imports the module that defines them, on first use.
"""

from __future__ import annotations

import warnings
from importlib import import_module
from importlib.metadata import version
from typing import TYPE_CHECKING

__version__ = version(__name__)

warnings.filterwarnings("ignore", module="azure.ai.ml")

if TYPE_CHECKING:
    from kedro_azureml_pipeline.config import KedroAzureMLConfig
    from kedro_azureml_pipeline.datasets.asset_dataset import AzureMLAssetDataset
    from kedro_azureml_pipeline.datasets.datastore_dataset import AzureMLDatastoreDataset
    from kedro_azureml_pipeline.datasets.pipeline_dataset import AzureMLPipelineDataset
    from kedro_azureml_pipeline.distributed import DistributedNodeConfig, distributed_job
    from kedro_azureml_pipeline.generator import AzureMLPipelineGenerator
    from kedro_azureml_pipeline.manager import KedroContextManager
    from kedro_azureml_pipeline.runner import AzurePipelinesRunner
    from kedro_azureml_pipeline.utils import CliContext

#: Public name -> the module that defines it.
_LAZY_EXPORTS: dict[str, str] = {
    "AzureMLAssetDataset": "kedro_azureml_pipeline.datasets.asset_dataset",
    "AzureMLDatastoreDataset": "kedro_azureml_pipeline.datasets.datastore_dataset",
    "AzureMLPipelineDataset": "kedro_azureml_pipeline.datasets.pipeline_dataset",
    "AzureMLPipelineGenerator": "kedro_azureml_pipeline.generator",
    "AzurePipelinesRunner": "kedro_azureml_pipeline.runner",
    "CliContext": "kedro_azureml_pipeline.utils",
    "DistributedNodeConfig": "kedro_azureml_pipeline.distributed",
    "KedroAzureMLConfig": "kedro_azureml_pipeline.config",
    "KedroContextManager": "kedro_azureml_pipeline.manager",
    "distributed_job": "kedro_azureml_pipeline.distributed",
}

__all__ = [
    "__version__",
    "AzureMLAssetDataset",
    "AzureMLDatastoreDataset",
    "AzureMLPipelineDataset",
    "AzureMLPipelineGenerator",
    "AzurePipelinesRunner",
    "CliContext",
    "DistributedNodeConfig",
    "KedroAzureMLConfig",
    "KedroContextManager",
    "distributed_job",
]


def __getattr__(name: str) -> object:
    """Import a public name from its defining module on first access."""
    module_name = _LAZY_EXPORTS.get(name)
    if module_name is None:
        msg = f"module {__name__!r} has no attribute {name!r}"
        raise AttributeError(msg)
    value = getattr(import_module(module_name), name)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    """List the public names so ``dir()`` and tab completion see the lazy exports."""
    return sorted(set(globals()) | set(__all__))
