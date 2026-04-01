"""Kedro AzureML Pipeline."""

from importlib.metadata import version

__version__ = version(__name__)

import warnings

warnings.filterwarnings("ignore", module="azure.ai.ml")

from kedro_azureml_pipeline.config import KedroAzureMLConfig  # noqa: E402
from kedro_azureml_pipeline.datasets.asset_dataset import AzureMLAssetDataset  # noqa: E402
from kedro_azureml_pipeline.datasets.pipeline_dataset import AzureMLPipelineDataset  # noqa: E402
from kedro_azureml_pipeline.distributed import DistributedNodeConfig, distributed_job  # noqa: E402
from kedro_azureml_pipeline.generator import AzureMLPipelineGenerator  # noqa: E402
from kedro_azureml_pipeline.manager import KedroContextManager  # noqa: E402
from kedro_azureml_pipeline.runner import AzurePipelinesRunner  # noqa: E402
from kedro_azureml_pipeline.utils import CliContext  # noqa: E402

__all__ = [
    "__version__",
    "AzureMLAssetDataset",
    "AzureMLPipelineDataset",
    "AzureMLPipelineGenerator",
    "AzurePipelinesRunner",
    "CliContext",
    "DistributedNodeConfig",
    "KedroAzureMLConfig",
    "KedroContextManager",
    "distributed_job",
]
