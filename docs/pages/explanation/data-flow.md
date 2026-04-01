# Data Flow Between Steps

When a Kedro pipeline runs locally, all nodes execute in the same process and share a filesystem. Data passes between nodes through the catalog: one node saves a dataset, the next node loads it. This works because every node can reach the same storage, whether that is a local directory, a database, or a cloud service.

Azure ML changes this picture. Each Kedro node runs as a separate pipeline step in its own container on managed compute. These containers do not share a local filesystem. The plugin's job is to reconnect the data flow so your pipeline produces the same results on cloud compute as it does locally, without you needing to change any pipeline logic.

## How datasets behave during remote execution

The plugin only needs to intervene for datasets that depend on a shared local filesystem. Datasets that manage their own storage (databases, cloud services, APIs) work unchanged because each container can reach them independently. This splits catalog entries into three categories:

- **[`AzureMLPipelineDataset`][kedro_azureml_pipeline.datasets.AzureMLPipelineDataset]**: intermediate data mounted between steps through temporary Azure ML storage.
- **[`AzureMLAssetDataset`][kedro_azureml_pipeline.datasets.AzureMLAssetDataset]**: versioned Data Assets registered in Azure ML.
- **Standard Kedro datasets**: any dataset not wrapped by the plugin (`ibis.TableDataset`, `pandas.SQLTableDataset`, `yaml.YAMLDataset`, S3/GCS/ABFS-backed datasets, etc.). These work without any plugin intervention. Datasets that connect to external services reach them directly from each step container, and datasets with local file paths travel inside the code snapshot the plugin uploads with each step.

### Mounted temporary storage (AzureMLPipelineDataset)

[`AzureMLPipelineDataset`][kedro_azureml_pipeline.datasets.AzureMLPipelineDataset] is designed for intermediate data: the outputs of one pipeline step that become inputs to the next. When the plugin compiles your pipeline, it tells Azure ML to mount a temporary storage path between the producing step and the consuming step. At runtime, [`AzurePipelinesRunner`][kedro_azureml_pipeline.runner.AzurePipelinesRunner] rewires the dataset's `root_dir` to point at the mount path.

The producing step saves its output through [`AzureMLPipelineDataset`][kedro_azureml_pipeline.datasets.AzureMLPipelineDataset] to a mounted path (`/mnt/azureml/outputs/...`). Azure ML then mounts the same data as an input on the consuming step (`/mnt/azureml/inputs/...`). The consuming step reads it through its own [`AzureMLPipelineDataset`][kedro_azureml_pipeline.datasets.AzureMLPipelineDataset] entry.

The underlying Kedro dataset (e.g. `pandas.ParquetDataset`) does the actual serialization. It just writes to a different directory than it would locally. This means your data format, compression, and schema stay exactly the same.

During local runs, [`AzureMLPipelineDataset`][kedro_azureml_pipeline.datasets.AzureMLPipelineDataset] behaves like a normal file-backed dataset. The `root_dir` defaults to `data/`, and the wrapper is transparent. There is no Azure ML interaction.

### Named Data Assets (AzureMLAssetDataset)

[`AzureMLAssetDataset`][kedro_azureml_pipeline.datasets.AzureMLAssetDataset] connects your catalog to Azure ML's Data Asset registry. Unlike temporary storage, Data Assets are versioned and persist across pipeline runs. They are the right choice for datasets that have an independent lifecycle, such as training data that gets updated separately from the pipeline or model artifacts that need to be tracked across experiments.

During remote execution, the plugin injects the asset's storage path as the `root_dir`, similar to how [`AzureMLPipelineDataset`][kedro_azureml_pipeline.datasets.AzureMLPipelineDataset] works. The key difference is that the path points to a registered, versioned location in Azure ML rather than a temporary mount.

During local runs, the behavior is more complex. The [`AzureMLLocalRunHook`][kedro_azureml_pipeline.hooks.AzureMLLocalRunHook] detects whether the dataset is a pipeline input (needs downloading from Azure ML) or an intermediate output (should be saved locally without Azure ML interaction):

- **Pipeline inputs**: The hook leaves the download behavior enabled. On first access, the dataset downloads the asset from your Azure ML workspace to a local directory structured as `{root_dir}/{asset_name}/{version}/{filepath}`. Subsequent runs reuse the cached copy.
- **Intermediate outputs**: The hook calls `as_local_intermediate()`, which disables downloading and assigns a `"local"` version marker. This prevents unnecessary Azure ML API calls for data that was just produced by a previous node.

This distinction matters because an [`AzureMLAssetDataset`][kedro_azureml_pipeline.datasets.AzureMLAssetDataset] entry might serve both roles depending on the pipeline graph: it could be an input to one pipeline and an output of another.

### Standard Kedro datasets

Any Kedro dataset that is not wrapped by [`AzureMLPipelineDataset`][kedro_azureml_pipeline.datasets.AzureMLPipelineDataset] or [`AzureMLAssetDataset`][kedro_azureml_pipeline.datasets.AzureMLAssetDataset] works in remote execution without plugin intervention. The plugin does not need to know about these datasets. They do not appear in the compiled Azure ML Pipeline YAML as inputs or outputs, and the runner does not rewire them.

Datasets that connect to external services (`ibis.TableDataset` querying a database, `pandas.SQLTableDataset` reading from PostgreSQL, datasets backed by S3, GCS, or Azure Blob Storage) work from inside an Azure ML step container as long as the container has network access and credentials. This is often the simplest path for data that already lives in an external system.

Datasets with local file paths (e.g. `yaml.YAMLDataset` pointing at `conf/parameters.yml`) are included in the code snapshot that the plugin uploads to each step. This works well for small configuration files, lookup tables, or static reference data that ships with your project. The code snapshot is uploaded once per step, so large files increase submission time and consume storage. Anything over a few megabytes should use [`AzureMLPipelineDataset`][kedro_azureml_pipeline.datasets.AzureMLPipelineDataset], [`AzureMLAssetDataset`][kedro_azureml_pipeline.datasets.AzureMLAssetDataset], or an externally-connected dataset instead.

## Local vs. remote behavior summary

| Dataset type | Local behavior | Remote behavior |
|---|---|---|
| [`AzureMLPipelineDataset`][kedro_azureml_pipeline.datasets.AzureMLPipelineDataset] | Reads/writes to `{root_dir}/{filepath}` as a normal file | Runner rewires `root_dir` to Azure ML mount path |
| [`AzureMLAssetDataset`][kedro_azureml_pipeline.datasets.AzureMLAssetDataset] (input) | Downloads from Azure ML, caches locally | Runner rewires `root_dir` to Azure ML asset path |
| [`AzureMLAssetDataset`][kedro_azureml_pipeline.datasets.AzureMLAssetDataset] (intermediate) | Saves locally with a `"local"` version, no download | Runner rewires `root_dir`, disables local-run logic |
| Standard Kedro dataset | Normal behavior (external connection, local file I/O, etc.) | Same behavior, no plugin intervention |

The key insight is that the plugin only intervenes for datasets that need inter-step coordination through Azure ML storage. Everything else, whether it is a database connection, a cloud storage path, or a config file in the code snapshot, works the same as during a local run.

## Connections

- [How to use data assets](../how-to/use-data-assets.md): practical guidance on configuring both plugin dataset types
- [Dataset reference](../reference/datasets.md): full parameter tables for [`AzureMLPipelineDataset`][kedro_azureml_pipeline.datasets.AzureMLPipelineDataset] and [`AzureMLAssetDataset`][kedro_azureml_pipeline.datasets.AzureMLAssetDataset]
- [Architecture overview](architecture.md): broader context on how data flow fits into the plugin's design
