# Migrate an Existing Kedro Project

In this tutorial we will take an existing Kedro project and connect it to Azure ML without changing any of your pipeline logic. Along the way we will discover how the plugin bridges between Kedro's execution model and Azure ML's managed compute, how datasets get rewired for cloud storage, and how the hook system keeps everything working transparently.

By the end, you will have your existing project running on Azure ML and understand the key concepts well enough to customize the setup for your own needs.

## Prerequisites

- An existing Kedro project (any starter or custom project)
- Python 3.11+
- An [Azure ML workspace](https://learn.microsoft.com/en-us/azure/machine-learning/concept-workspace) with at least one compute cluster
- Azure credentials configured (`az login`)
- An Azure ML environment with your project's dependencies installed

!!! tip "New to Azure ML?"

    [Azure ML Pipelines](https://learn.microsoft.com/en-us/azure/machine-learning/concept-ml-pipelines) let you run pipeline steps on managed cloud compute. You will need an Azure subscription, a workspace, and a compute cluster.

## Step 1: Install the plugin

From your project root:

=== "pip"
    ```bash
    pip install kedro-azureml-pipeline
    ```
=== "uv"
    ```bash
    uv add kedro-azureml-pipeline
    ```

Verify the installation:

```bash
kedro azureml --help
```

You should see output starting with:

```text
Usage: kedro azureml [OPTIONS] COMMAND [ARGS]...
```

## Step 2: Understand the hook system

Kedro uses a hook system that lets plugins tap into the pipeline lifecycle: before and after catalogs load, before and after each node runs, and so on. The plugin provides two hooks:

- [`AzureMLLocalRunHook`][kedro_azureml_pipeline.hooks.AzureMLLocalRunHook] intercepts catalog creation so that Azure ML dataset entries resolve to the right paths whether you are running locally or on cloud compute.
- [`MlflowAzureMLHook`][kedro_azureml_pipeline.hooks.MlflowAzureMLHook] coordinates with [Kedro-MLflow](https://kedro-mlflow.readthedocs.io/) so that MLflow tracking calls are routed to your Azure ML workspace's tracking endpoint during remote runs.

Both hooks are auto-registered via Python entry points when you install the package. You do not need to add them to `HOOKS` in `settings.py` as Kedro discovers them automatically.

## Step 3: Initialize the configuration

```bash
kedro azureml init
```

You should see:

```text
Creating conf/base/azureml.yml...
Creating .amlignore...
```

## Step 4: Configure your workspace

Open `conf/base/azureml.yml` and fill in your Azure ML details:

```yaml
workspace:
  __default__:
    subscription_id: "<your-subscription-id>"
    resource_group: "<your-resource-group>"
    name: "<your-workspace-name>"

compute:
  __default__:
    cluster_name: "<your-cluster-name>"

execution:
  environment: "<your-aml-environment>@latest"
  code_directory: "."
```

The `__default__` key is special: it is the fallback workspace and compute that jobs use unless they specify otherwise. Later, you can define named entries for dev, staging, and production workspaces alongside `__default__`.

The `execution.code_directory` tells the plugin which folder to upload as the code snapshot for each pipeline step. Setting it to `"."` uploads your entire project root. The `.amlignore` file (created during `kedro azureml init`) controls which files are excluded from the upload, similar to `.gitignore`.

!!! tip "Finding your Azure details"

    In the [Azure Portal](https://portal.azure.com/), open your Azure ML workspace. The **Overview** page shows the subscription ID, resource group, and workspace name. Compute clusters are listed under **Manage > Compute > Compute clusters**.

## Step 5: Update your catalog

This is the most important conceptual step. When Kedro runs locally, each node reads and writes data through the catalog using local file paths. When the plugin submits your pipeline to Azure ML, each node runs as a separate container on cloud compute so the nodes can no longer share a local filesystem.

The plugin solves this with two wrapper datasets:

- **[`AzureMLPipelineDataset`][kedro_azureml_pipeline.datasets.AzureMLPipelineDataset]**: for intermediate data that passes between pipeline steps. Azure ML mounts a temporary storage path between the producing step and the consuming step.
- **[`AzureMLAssetDataset`][kedro_azureml_pipeline.datasets.AzureMLAssetDataset]**: for data registered as a versioned Azure ML Data Asset. The asset path is resolved at runtime.

Wrap any dataset that passes data between separate pipeline steps with [`AzureMLPipelineDataset`][kedro_azureml_pipeline.datasets.AzureMLPipelineDataset]:

```yaml
# Before (standard Kedro dataset)
preprocessed_shuttles:
  type: pandas.ParquetDataset
  filepath: data/02_intermediate/preprocessed_shuttles.pq

# After (Azure ML pipeline-aware)
preprocessed_shuttles:
  type: kedro_azureml_pipeline.datasets.AzureMLPipelineDataset
  dataset:
    type: pandas.ParquetDataset
    filepath: preprocessed_shuttles.pq
```

Notice that the `filepath` is now relative because the plugin manages the root directory during remote execution. Locally, the dataset still behaves like a normal file-backed dataset.

For datasets backed by versioned Azure ML Data Assets, use [`AzureMLAssetDataset`][kedro_azureml_pipeline.datasets.AzureMLAssetDataset] instead:

```yaml
model_inputs:
  type: kedro_azureml_pipeline.datasets.AzureMLAssetDataset
  azureml_dataset: "my-model-inputs"
  azureml_type: "uri_folder"
  dataset:
    type: pandas.ParquetDataset
    filepath: "data.parquet"
```

!!! note "You don't need to wrap every dataset"

    Only wrap datasets that pass data between separate pipeline steps or reference Azure ML Data Assets.

## Step 6: Define a job

A job tells the plugin which Kedro pipeline to submit and where to run it. Add a `jobs` section to `conf/base/azureml.yml`:

```yaml
jobs:
  main:
    pipeline:
      pipeline_name: "__default__"
    experiment_name: "my-project"
    display_name: "Main pipeline"
```

The `pipeline_name` maps to a registered Kedro pipeline. `"__default__"` is the pipeline Kedro runs when you call `kedro run` without a `--pipeline` flag.

If your project has multiple pipelines, you can define one job per pipeline. You can also filter which nodes to include using the same arguments Kedro supports: `tags`, `node_names`, `from_nodes`, `to_nodes`, and `node_namespaces`:

```yaml
jobs:
  training:
    pipeline:
      pipeline_name: "training"
    experiment_name: "my-project"
  inference:
    pipeline:
      pipeline_name: "inference"
      tags: ["production"]
    experiment_name: "my-project"
```

Each job inherits the `__default__` workspace and compute unless you override them explicitly.

## Step 7: Verify locally

Before submitting to Azure ML, let's confirm your project still runs locally with the new dataset wrappers:

```bash
kedro run
```

The pipeline should complete exactly as before. This is the key insight: [`AzureMLPipelineDataset`][kedro_azureml_pipeline.datasets.AzureMLPipelineDataset] and [`AzureMLAssetDataset`][kedro_azureml_pipeline.datasets.AzureMLAssetDataset] are transparent wrappers that behave like normal Kedro datasets during local runs. The plugin only activates its cloud behavior when you submit through `kedro azureml run`.

If this fails, the issue is in the catalog changes (most likely a `filepath` that needs adjusting), not the plugin itself.

## Step 8: Submit to Azure ML

Now let's send the pipeline to the cloud:

```bash
kedro azureml run -j main
```

After a moment, you should see a run URL printed to the terminal. Open it in your browser to see the pipeline running in Azure ML Studio. Notice that each Kedro node appears as a separate step in the Azure ML pipeline graph. The plugin automatically translated your Kedro pipeline structure into Azure ML's execution model.

!!! note

    You can add `--wait-for-completion` to block until the run finishes.

## What we built

You have migrated an existing Kedro project to run on Azure ML without changing any pipeline logic. Along the way, we covered several important concepts:

- **Hooks** bridge the gap between Kedro's lifecycle and Azure ML's execution model
- **Dataset wrappers** ([`AzureMLPipelineDataset`][kedro_azureml_pipeline.datasets.AzureMLPipelineDataset] and [`AzureMLAssetDataset`][kedro_azureml_pipeline.datasets.AzureMLAssetDataset]) make data flow work across separate cloud containers while staying transparent during local runs
- **Jobs** map your Kedro pipelines to Azure ML experiments with their own compute and workspace settings
- **Configuration** lives in `azureml.yml`, layered through Kedro's config system just like your catalog and parameters

## Next steps

- [How to use data assets](../how-to/use-data-assets.md) for versioned Azure ML Data Assets
- [How to schedule pipelines](../how-to/schedule-pipelines.md) for recurring cron and recurrence schedules
- [Compile and inspect](../how-to/compile-and-inspect.md) for verifying pipeline YAML before submitting
- [Datasets reference](../reference/datasets.md) for the full parameter tables
- [Configuration reference](../reference/configuration.md) for all `azureml.yml` fields
