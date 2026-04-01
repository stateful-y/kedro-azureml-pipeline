# How to Compile and Inspect Pipelines

This guide shows how to compile Kedro pipelines into Azure ML Pipeline YAML definitions and inspect them before submitting a job.

## Prerequisites

- The Kedro AzureML Pipeline plugin installed and configured (see [Getting Started](../tutorials/getting-started.md))
- At least one job defined under `jobs:` in `azureml.yml`

## Compile a job to YAML

```bash
kedro azureml compile -j training
```

This writes `pipeline.yaml` (the default output path) containing the full Azure ML Pipeline definition.

## Specify a custom output path

```bash
kedro azureml compile -j training -o my-pipeline.yaml
```

When compiling multiple jobs, the output file is suffixed with the job name:

```bash
kedro azureml compile -j training -j validation -o pipeline.yaml
# produces: pipeline_training.yaml, pipeline_validation.yaml
```

## What to look for in the output

Open the generated YAML and check:

- **Component list**: Each Kedro node should appear as a separate component. Missing nodes may indicate filter options in the job config.
- **Environment variables**: Verify that `KEDRO_AZUREML_MLFLOW_ENABLED` is set if you use MLflow integration.
- **Inputs and outputs**: Each component lists its Azure ML-managed inputs and outputs. These correspond to your catalog entries wrapped in [`AzureMLPipelineDataset`][kedro_azureml_pipeline.datasets.AzureMLPipelineDataset] or [`AzureMLAssetDataset`][kedro_azureml_pipeline.datasets.AzureMLAssetDataset].
- **Compute target**: Confirm the correct cluster is referenced.
- **Distributed configuration**: Nodes decorated with [`@distributed_job`][kedro_azureml_pipeline.distributed.distributed_job] should show `distribution` and `resources` sections.

## Debug pipeline definition issues

If a node is missing or configured incorrectly:

1. Check the `jobs.<name>.pipeline` filter options in `azureml.yml` (e.g. `tags`, `node_names`, `from_nodes`, `to_nodes`).
2. Verify the node is registered in the Kedro pipeline:

    ```bash
    kedro registry list
    ```

3. Compile with runtime parameter overrides to test different configurations:

    ```bash
    kedro azureml compile -j training --params '{"learning_rate": 0.01}'
    ```

4. Inject extra environment variables:

    ```bash
    kedro azureml compile -j training --env-var DEBUG=1
    ```

## Use compile before run

Compiling before submitting helps catch configuration errors without incurring Azure ML compute costs:

```bash
# 1. Compile and inspect
kedro azureml compile -j training -o check.yaml
cat check.yaml

# 2. Submit when satisfied
kedro azureml run -j training
```

## See also

- [CLI reference](../reference/cli.md#kedro-azureml-compile) for all `compile` flags
- [Configuration reference](../reference/configuration.md#jobs) for job filter options
- [Architecture overview](../explanation/architecture.md) for how compilation works internally
