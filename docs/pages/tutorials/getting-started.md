# Getting Started

In this tutorial we will take a Kedro project, connect it to Azure ML, and submit a pipeline run to cloud compute. Along the way we will install the plugin, configure a workspace, define a job, and see it running in Azure ML Studio.

## Prerequisites

Before you begin, make sure you have:

- Python 3.11+
- An [Azure ML workspace](https://learn.microsoft.com/en-us/azure/machine-learning/concept-workspace) with at least one compute cluster
- Azure credentials configured (`az login`)
- An Azure ML environment created in your workspace (e.g. `my-env@latest`)

## Step 1 - Create a Kedro project

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

## Step 2 - Install the plugin

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

## Step 3 - Register the hooks

Open `src/<package_name>/settings.py` and add:

```python
from kedro_azureml_pipeline.hooks import azureml_local_run_hook

HOOKS = (azureml_local_run_hook,)
```

## Step 4 - Initialize the configuration

From the project root, run:

```bash
kedro azureml init
```

You should see:

```text
Creating conf/base/azureml.yml...
Creating .amlignore...
```

Notice that two new files appeared: `conf/base/azureml.yml` for plugin settings and `.amlignore` for controlling which files are uploaded to Azure ML.

## Step 5 - Configure your workspace

Open `conf/base/azureml.yml` and replace the placeholders:

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

## Step 6 - Define a job

Add a `jobs` section to the same `azureml.yml` file:

```yaml
jobs:
  training:
    pipeline:
      pipeline_name: "__default__"
    experiment_name: "spaceflights-training"
    display_name: "Training pipeline"
```

## Step 7 - Run on Azure ML

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

## What we built

You have submitted a Kedro pipeline to Azure ML managed compute. Along the way, you:

- Installed `kedro-azureml-pipeline` and registered its hook
- Configured a workspace, compute target, and environment in `azureml.yml`
- Defined a job that maps a Kedro pipeline to an Azure ML pipeline submission
- Submitted the job and saw it running in Azure ML Studio

## Next steps

- [How to schedule pipelines](../how-to/schedule-pipelines.md) - set up recurring cron and recurrence schedules
- [Configuration reference](../reference/configuration.md) - all `azureml.yml` fields
- [Architecture overview](../explanation/architecture.md) - how the plugin translates Kedro to Azure ML
