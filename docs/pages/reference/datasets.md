# Dataset Reference

Catalog examples and runtime behavior for the two dataset types provided by the plugin. For full constructor signatures and parameter details, see the auto-generated API pages: [`AzureMLAssetDataset`][kedro_azureml_pipeline.datasets.AzureMLAssetDataset] and [`AzureMLPipelineDataset`][kedro_azureml_pipeline.datasets.AzureMLPipelineDataset].

---

## `AzureMLAssetDataset`

```text
kedro_azureml_pipeline.datasets.AzureMLAssetDataset
```

Kedro dataset backed by an Azure ML Data Asset. Supports both `uri_folder` and `uri_file` asset types. During local runs, the asset is downloaded automatically. During remote runs, Azure ML mounts the asset path.

Inherits from [`AzureMLPipelineDataset`][kedro_azureml_pipeline.datasets.AzureMLPipelineDataset] and Kedro's `AbstractVersionedDataset`.

### Catalog example

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

### Properties

| Property | Returns | Description |
|---|---|---|
| `path` | `Path` | Full resolved path to the underlying file. During local runs, includes the asset name and version as path segments. |
| `download_path` | `str` | Target directory for downloading the asset. Returns the parent directory for file assets, or the path itself for folder assets. |
| `azure_config` | `WorkspaceConfig` | Current Azure ML workspace configuration (set by [`AzureMLLocalRunHook`][kedro_azureml_pipeline.hooks.AzureMLLocalRunHook]). |

### Behavior

- **Local runs**: Downloads the asset from Azure ML on first `_load()` call. The download path is `<root_dir>/<azureml_dataset>/<version>/<filepath>`.
- **Remote runs**: Azure ML mounts the asset at a path injected by [`AzurePipelinesRunner`][kedro_azureml_pipeline.runner.AzurePipelinesRunner]. No download occurs.
- **Versioning**: Handled by Azure ML Data Asset versions, not Kedro's built-in versioning. Setting `versioned: true` on the underlying dataset raises an error.
- **Distributed nodes**: On non-master nodes, `_save()` is skipped (inherited from [`AzureMLPipelineDataset`][kedro_azureml_pipeline.datasets.AzureMLPipelineDataset]).

---

## `AzureMLPipelineDataset`

```text
kedro_azureml_pipeline.datasets.AzureMLPipelineDataset
```

Dataset for passing data between Azure ML pipeline steps. Wraps an underlying Kedro dataset and rewrites its file path to Azure ML compute mount paths during remote execution.

Inherits from Kedro's `AbstractDataset`.

### Catalog example

```yaml
intermediate_features:
  type: kedro_azureml_pipeline.datasets.AzureMLPipelineDataset
  dataset:
    type: pandas.ParquetDataset
    filepath: "features.parquet"
```

### Properties

| Property | Returns | Description |
|---|---|---|
| `path` | `Path` | Combined `root_dir` and underlying filepath. |

### Behavior

- **Local runs**: Behaves like a normal file-backed dataset. No Azure ML calls.
- **Remote runs**: [`AzurePipelinesRunner`][kedro_azureml_pipeline.runner.AzurePipelinesRunner] rewrites `root_dir` to an Azure ML-managed mount path. Data flows between steps through temporary Azure ML storage.
- **Distributed nodes**: On non-master nodes (rank != 0), `_save()` is skipped to avoid duplicate writes.
- **Versioning**: Not supported on the underlying dataset. Setting `versioned: true` raises an error.

---

## See also

- [How to use data assets](../how-to/use-data-assets.md) for usage guidance and examples
- [Architecture overview](../explanation/architecture.md#data-flow-between-steps) for how data flows between pipeline steps
- [`AzureMLAssetDataset`][kedro_azureml_pipeline.datasets.AzureMLAssetDataset] and [`AzureMLPipelineDataset`][kedro_azureml_pipeline.datasets.AzureMLPipelineDataset] API for full constructor signatures
