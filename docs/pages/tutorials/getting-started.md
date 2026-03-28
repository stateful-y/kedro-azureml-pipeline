# Getting Started with Kedro AzureML Pipeline

In this tutorial you will deploy a Kedro project to Azure ML Pipelines from scratch. You will create a Kedro project from a starter template, install and configure the plugin, and submit your first pipeline run to Azure ML managed compute.

By the end you will have:

- A working Kedro project connected to an Azure ML workspace
- Your pipeline executing on cloud compute
- An understanding of how the plugin bridges Kedro and Azure ML

## Prerequisites

Before you begin, make sure you have:

- Python 3.11+
- An [Azure ML workspace](https://learn.microsoft.com/en-us/azure/machine-learning/concept-workspace) with at least one compute cluster
- Azure credentials configured - run `az login` or configure a service principal
- An Azure ML environment created in your workspace (e.g. `my-env@latest`)

## Step 1 - Create a Kedro project

Start with the `spaceflights-pandas` starter. If you already have a Kedro project, skip this step.

```bash
kedro new --starter=spaceflights-pandas
```

Follow the prompts. Once done, install the project dependencies:

=== "pip"
    ```bash
    cd spaceflights-pandas
    pip install -r requirements.txt
    ```
=== "uv"
    ```bash
    cd spaceflights-pandas
    uv sync
    ```

## Step 2 - Install the plugin

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

## Step 3 - Register the hooks

The plugin provides `azureml_local_run_hook`, which ensures that data assets are resolved correctly during local runs. Register it in `src/<package_name>/settings.py`:

```python
from kedro_azureml_pipeline.hooks import azureml_local_run_hook

HOOKS = (azureml_local_run_hook,)
```

This is the only code change required in your Kedro project. All other existing hooks, catalog entries, and pipeline definitions remain exactly as-is.

## Step 4 - Initialize the configuration

From your Kedro project root:

```bash
kedro azureml init
```

This creates two files:

- `conf/base/azureml.yml` - workspace, compute, and execution settings (pre-filled with placeholders)
- `.amlignore` - controls which local files are excluded from the code upload to Azure ML

## Step 5 - Configure your workspace

Open `conf/base/azureml.yml` and replace the placeholders with your Azure details:

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

The `workspace.__default__` and `compute.__default__` entries are required. The `execution.environment` must reference an existing Azure ML environment in your workspace.

Setting `code_directory: "."` tells the plugin to upload your project code as a snapshot before each run. Set it to `null` if your environment already bundles all necessary code.

## Step 6 - Define a job

Add a `jobs` section to `azureml.yml`:

```yaml
jobs:
  training:
    pipeline:
      pipeline_name: "__default__"
    experiment_name: "spaceflights-training"
    display_name: "Training pipeline"
```

Each job maps a named Kedro pipeline to an Azure ML pipeline submission. The `pipeline_name: "__default__"` value runs the default Kedro pipeline.

## Step 7 - Run on Azure ML

Submit the job:

```bash
kedro azureml run -j training
```

This compiles your Kedro pipeline into an Azure ML pipeline definition, uploads your code snapshot, and submits the job. You will see the run URL printed to the terminal. Open Azure ML Studio to monitor progress.

To block your terminal until the run completes:

```bash
kedro azureml run -j training --wait-for-completion
```

Congratulations - your Kedro pipeline is now running on Azure ML managed compute.

## What's next

- [Configuration reference](../reference/configuration.md) - all `azureml.yml` fields for workspaces, compute, jobs, and environments
- [How to schedule pipelines](../how-to/schedule-pipelines.md) - set up recurring cron and recurrence schedules
- [CLI reference](../reference/cli.md) - all flags for `run`, `compile`, `schedule`, and other commands
- [Architecture overview](../explanation/architecture.md) - understand how Kedro and Azure ML fit together
