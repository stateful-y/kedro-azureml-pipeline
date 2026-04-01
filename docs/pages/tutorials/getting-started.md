# Getting Started

In this tutorial we will take a Kedro project, connect it to Azure ML, and submit a pipeline run to cloud compute. Along the way we will install the plugin, configure a workspace, define a job, and see it running in Azure ML Studio.

## Prerequisites

Before you begin, make sure you have:

- Python 3.11+
- An [Azure ML workspace](https://learn.microsoft.com/en-us/azure/machine-learning/concept-workspace) with at least one compute cluster
- Azure credentials configured (`az login`)
- An Azure ML environment created in your workspace (e.g. `my-env@latest`)

!!! tip "New to Kedro or Azure ML?"

    **Coming from Azure ML?** [Kedro](https://docs.kedro.org/) is a Python framework for building reproducible data science pipelines. You define nodes (functions) and a catalog (data sources), and Kedro handles execution order and data passing.

    **Coming from Kedro?** [Azure ML Pipelines](https://learn.microsoft.com/en-us/azure/machine-learning/concept-ml-pipelines) let you run pipeline steps on managed cloud compute. You will need an Azure subscription, a workspace, and a compute cluster.

## Step 1: Create a Kedro project

We will use the `spaceflights-pandas` starter:

```bash
kedro new --starter=spaceflights-pandas
```

Follow the prompts, then install the project dependencies:

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

## Step 2: Install the plugin

=== "pip"
    ```bash
    pip install kedro-azureml-pipeline
    ```
=== "uv"
    ```bash
    uv add kedro-azureml-pipeline
    ```

Let's verify the installation:

```bash
kedro azureml --help
```

You should see output starting with:

```text
Usage: kedro azureml [OPTIONS] COMMAND [ARGS]...
```

## Step 3: Initialize the configuration

The plugin ships two hooks ([`AzureMLLocalRunHook`][kedro_azureml_pipeline.hooks.AzureMLLocalRunHook] and [`MlflowAzureMLHook`][kedro_azureml_pipeline.hooks.MlflowAzureMLHook]) that are auto-registered via Python entry points. Kedro automatically discovers them when the package is installed.

From the project root, run:

```bash
kedro azureml init
```

You should see:

```text
Creating conf/base/azureml.yml...
Creating .amlignore...
```

Notice that two new files appeared:

- `conf/base/azureml.yml`: plugin settings (workspace, compute, jobs)
- `.amlignore`: controls which files are excluded from code uploads (similar to `.gitignore`)

The plugin supports two deployment flows. Choose the one that fits your setup:

- **Code upload**: the plugin uploads a snapshot of your project to Azure ML on every run. Simplest way to get started.
- **Pre-built environment**: your code is already installed inside the Azure ML environment (Docker image). Faster for large projects since nothing is uploaded.

## Step 4: Configure your workspace

Open `conf/base/azureml.yml` and replace the placeholders. The `execution` section differs depending on which deployment flow you chose:

=== "Code upload"

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

    With `code_directory: "."`, the plugin snapshots your project directory and uploads it to Azure ML. The `.amlignore` file controls which files are excluded from the upload.

=== "Pre-built environment"

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
      working_directory: "/home/kedro_docker"
    ```

    With no `code_directory`, nothing is uploaded. The `working_directory` tells Azure ML where your pre-installed code lives inside the container. Your Docker image must already contain the Kedro project and all dependencies.

!!! tip "Finding your Azure details"

    In the [Azure Portal](https://portal.azure.com/), open your Azure ML workspace. The **Overview** page shows the subscription ID, resource group, and workspace name. Compute clusters are listed under **Manage > Compute > Compute clusters**.

## Step 5: Define a job

Add a `jobs` section to the same `azureml.yml` file:

```yaml
jobs:
  training:
    pipeline:
      pipeline_name: "__default__"
    experiment_name: "spaceflights-training"
    display_name: "Training pipeline"
```

## Step 6: Run on Azure ML

Now let's submit the job:

```bash
kedro azureml run -j training
```

After a moment, you should see a run URL printed to the terminal. Open it in your browser to see the pipeline running in Azure ML Studio:

```text
https://ml.azure.com/runs/<run-id>?wsid=...
```

To block your terminal until the run completes, add `--wait-for-completion`:

```bash
kedro azureml run -j training --wait-for-completion
```

!!! note

    Azure ML compute is billed while your job is running. The spaceflights starter pipeline typically completes in a few minutes on a small cluster.

## Summary

You have submitted a Kedro pipeline to Azure ML managed compute. Along the way, you:

- Installed `kedro-azureml-pipeline`
- Configured a workspace, compute target, and environment in `azureml.yml`
- Defined a job that maps a Kedro pipeline to an Azure ML pipeline submission
- Submitted the job and saw it running in Azure ML Studio

## Next steps

- [How to use data assets](../how-to/use-data-assets.md) for versioned Azure ML Data Assets
- [How to schedule pipelines](../how-to/schedule-pipelines.md) for recurring cron and recurrence schedules
- [Compile and inspect](../how-to/compile-and-inspect.md) for verifying pipeline YAML before submitting
- [Deploy from CI/CD](../how-to/deploy-from-cicd.md) for automating submissions
- [How to authenticate](../how-to/authenticate.md) for configuring Azure credentials in different environments
- [Configuration reference](../reference/configuration.md) for all `azureml.yml` fields
- [Architecture overview](../explanation/architecture.md) for how the plugin translates Kedro to Azure ML
