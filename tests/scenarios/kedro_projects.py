"""Pre-built Kedro project scenario options for Azure ML integration tests."""

from __future__ import annotations

from typing import Any

from .project_factory import KedroProjectOptions


def pipeline_registry_default() -> str:
    """Simple 3-node linear pipeline for basic integration tests."""
    return """
from kedro.pipeline import Pipeline, node


def identity(arg):
    return arg


def register_pipelines():
    pipeline = Pipeline(
        [
            node(identity, ["input_ds"], "intermediate_ds", name="node0"),
            node(identity, ["intermediate_ds"], "output_ds", name="node1"),
            node(identity, ["intermediate_ds"], "output2_ds", name="node2"),
        ],
    )
    return {"__default__": pipeline}
"""


def default_azureml_config() -> dict[str, Any]:
    """Minimal azureml.yml config for tests."""
    return {
        "workspace": {
            "__default__": {
                "subscription_id": "test-sub-id",
                "resource_group": "test-rg",
                "name": "test-workspace",
            }
        },
        "compute": {
            "__default__": {
                "cluster_name": "cpu-cluster",
            }
        },
        "execution": {
            "environment": "test-env:1",
        },
        "jobs": {
            "__default__": {
                "pipeline": {"pipeline_name": "__default__"},
            }
        },
    }


def options_basic_pipeline(env: str = "base") -> KedroProjectOptions:
    """Minimal pipeline with azureml config."""
    catalog = {
        "input_ds": {"type": "MemoryDataset"},
        "intermediate_ds": {"type": "MemoryDataset"},
        "output_ds": {"type": "MemoryDataset"},
        "output2_ds": {"type": "MemoryDataset"},
    }
    return KedroProjectOptions(
        env=env,
        catalog=catalog,
        azureml=default_azureml_config(),
        pipeline_registry_py=pipeline_registry_default(),
    )


def options_with_compute_tags(env: str = "base") -> KedroProjectOptions:
    """Pipeline with compute-tagged nodes for multi-cluster tests."""
    opts = options_basic_pipeline(env)
    opts.pipeline_registry_py = """
from kedro.pipeline import Pipeline, node


def identity(arg):
    return arg


def register_pipelines():
    pipeline = Pipeline(
        [
            node(identity, ["input_ds"], "intermediate_ds", name="node0", tags=["compute-2"]),
            node(identity, ["intermediate_ds"], "output_ds", name="node1"),
            node(identity, ["intermediate_ds"], "output2_ds", name="node2"),
        ],
    )
    return {"__default__": pipeline}
"""
    return opts


def options_with_azureml_datasets(env: str = "base") -> KedroProjectOptions:
    """Pipeline using AzureMLAssetDataset entries in the catalog."""
    catalog = {
        "input_ds": {
            "type": "kedro_azureml_pipeline.datasets.AzureMLAssetDataset",
            "azureml_dataset": "test-dataset",
            "dataset": {"type": "pandas.CSVDataset"},
        },
        "intermediate_ds": {"type": "MemoryDataset"},
        "output_ds": {"type": "MemoryDataset"},
    }
    return KedroProjectOptions(
        env=env,
        catalog=catalog,
        azureml=default_azureml_config(),
        pipeline_registry_py=pipeline_registry_default(),
    )


def options_with_schedule(env: str = "base") -> KedroProjectOptions:
    """Pipeline with a cron schedule configured."""
    config = default_azureml_config()
    config["jobs"]["__default__"]["schedule"] = "daily"
    config["schedules"] = {
        "daily": {
            "cron": {
                "expression": "0 6 * * *",
                "time_zone": "UTC",
            }
        }
    }
    return KedroProjectOptions(
        env=env,
        catalog={
            "input_ds": {"type": "MemoryDataset"},
            "intermediate_ds": {"type": "MemoryDataset"},
            "output_ds": {"type": "MemoryDataset"},
            "output2_ds": {"type": "MemoryDataset"},
        },
        azureml=config,
        pipeline_registry_py=pipeline_registry_default(),
    )
