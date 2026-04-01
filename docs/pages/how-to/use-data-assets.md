# How to Use Data Assets

This guide shows how to integrate Azure ML Data Assets into your Kedro catalog using [`AzureMLAssetDataset`][kedro_azureml_pipeline.datasets.AzureMLAssetDataset] and [`AzureMLPipelineDataset`][kedro_azureml_pipeline.datasets.AzureMLPipelineDataset].

## Prerequisites

- Azure credentials configured for local runs
- An Azure ML workspace configured in `azureml.yml`

## Use `AzureMLAssetDataset` for versioned data assets

[`AzureMLAssetDataset`][kedro_azureml_pipeline.datasets.AzureMLAssetDataset] reads and writes named Azure ML Data Assets (`uri_file` or `uri_folder`). It wraps any standard Kedro dataset and resolves the asset's storage path automatically.

Add an entry to your `conf/base/catalog.yml`:

```yaml
model_inputs:
  type: kedro_azureml_pipeline.datasets.AzureMLAssetDataset
  azureml_dataset: "my-model-inputs"
  azureml_type: "uri_folder"
  dataset:
    type: pandas.ParquetDataset
    filepath: "data.parquet"
```

The `azureml_dataset` field is the name of the Data Asset in Azure ML. The `dataset` block is an ordinary Kedro dataset definition, so any type that accepts a `filepath` argument works here.

### Use `uri_file` for single-file assets

```yaml
training_config:
  type: kedro_azureml_pipeline.datasets.AzureMLAssetDataset
  azureml_dataset: "training-config"
  azureml_type: "uri_file"
  dataset:
    type: yaml.YAMLDataset
    filepath: "config.yml"
```

### Pin a specific asset version

```yaml
model_inputs:
  type: kedro_azureml_pipeline.datasets.AzureMLAssetDataset
  azureml_dataset: "my-model-inputs"
  azureml_type: "uri_folder"
  azureml_version: "3"
  dataset:
    type: pandas.ParquetDataset
    filepath: "data.parquet"
```

Omitting `azureml_version` uses the latest available version.

### Local behavior

During local runs (`kedro run`), the [`AzureMLLocalRunHook`][kedro_azureml_pipeline.hooks.AzureMLLocalRunHook] downloads the asset to `root_dir` on first access. If the asset has not been downloaded yet, the hook fetches it from your Azure ML workspace, so Azure credentials must be available. Subsequent runs reuse the local copy.

### Override the local root directory

During local runs, the plugin downloads asset data to `root_dir`. Override it if needed:

```yaml
model_inputs:
  type: kedro_azureml_pipeline.datasets.AzureMLAssetDataset
  azureml_dataset: "my-model-inputs"
  azureml_type: "uri_folder"
  root_dir: "data/01_raw"
  dataset:
    type: pandas.ParquetDataset
    filepath: "data.parquet"
```

## Use `AzureMLPipelineDataset` for inter-step data passing

[`AzureMLPipelineDataset`][kedro_azureml_pipeline.datasets.AzureMLPipelineDataset] passes data between Kedro nodes that run as separate Azure ML pipeline steps. Rather than referencing a named Azure ML Data Asset, Azure ML mounts a temporary storage path between steps. Use this for intermediate data that does not need to be versioned or registered as an asset.

```yaml
intermediate_features:
  type: kedro_azureml_pipeline.datasets.AzureMLPipelineDataset
  dataset:
    type: pandas.ParquetDataset
    filepath: "features.parquet"
```

The `root_dir` and `filepath_arg` parameters work the same as in [`AzureMLAssetDataset`][kedro_azureml_pipeline.datasets.AzureMLAssetDataset].

During local runs, [`AzureMLPipelineDataset`][kedro_azureml_pipeline.datasets.AzureMLPipelineDataset] behaves like a normal file-backed dataset with no Azure ML calls.

### When to use each type

| Situation | Dataset type |
|---|---|
| Input/output data registered as a versioned asset in Azure ML | [`AzureMLAssetDataset`][kedro_azureml_pipeline.datasets.AzureMLAssetDataset] |
| Intermediate data passing between pipeline steps | [`AzureMLPipelineDataset`][kedro_azureml_pipeline.datasets.AzureMLPipelineDataset] |

See the [architecture overview](../explanation/architecture.md) for details on how data flows between steps during remote execution.

## See also

- [Datasets reference](../reference/datasets.md) for the full parameter tables
- [Configuration reference](../reference/configuration.md) for workspace and credential settings
- [`AzureMLAssetDataset`][kedro_azureml_pipeline.datasets.AzureMLAssetDataset] API for the auto-generated class documentation
- [`AzureMLPipelineDataset`][kedro_azureml_pipeline.datasets.AzureMLPipelineDataset] API for the auto-generated class documentation
