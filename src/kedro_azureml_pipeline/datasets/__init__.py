"""Kedro datasets for Azure ML pipeline data passing."""

from kedro_azureml_pipeline.datasets.asset_dataset import AzureMLAssetDataset
from kedro_azureml_pipeline.datasets.pipeline_dataset import AzureMLPipelineDataset

__all__ = [
    "AzureMLAssetDataset",
    "AzureMLPipelineDataset",
]
