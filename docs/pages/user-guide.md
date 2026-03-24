# User Guide

This guide covers configuration, CLI commands, and advanced features of Kedro AzureML Pipeline.

## Configuration reference

All settings live in `conf/<env>/azureml.yml`. The top-level structure is defined by `KedroAzureMLConfig`:

```yaml
workspace:    # required, named Azure ML workspace definitions
compute:      # required, named compute cluster definitions
execution:    # optional, environment and code upload settings
schedules:    # optional, reusable schedule definitions
jobs:         # optional, named job definitions
```

### Workspaces

```yaml
workspace:
  __default__:
    subscription_id: "00000000-0000-0000-0000-000000000000"
    resource_group: "rg-dev"
    name: "aml-dev"
  prod:
    subscription_id: "11111111-1111-1111-1111-111111111111"
    resource_group: "rg-prod"
    name: "aml-prod"
```

A `__default__` entry is mandatory. Jobs reference a workspace by name; omitting the workspace falls back to `__default__`.

### Compute

```yaml
compute:
  __default__:
    cluster_name: "cpu-cluster"
  gpu:
    cluster_name: "gpu-cluster"
```

A `__default__` entry is mandatory. Jobs can override the compute target by referencing a named entry.

### Execution

```yaml
execution:
  environment: "my-env@latest"
  code_directory: "."           # path to upload, or null to disable
  working_directory: /home/kedro  # working dir inside the container
```

| Field | Default | Description |
|---|---|---|
| `environment` | `null` | Azure ML environment name (e.g. `my-env@latest`) |
| `code_directory` | `null` | Local directory to upload as code snapshot; `null` disables code upload |
| `working_directory` | `null` | Working directory inside the compute container |

### Jobs

Each entry in `jobs` maps to an Azure ML pipeline submission:

```yaml
jobs:
  training:
    pipeline:
      pipeline_name: "__default__"
      tags: ["training"]
    experiment_name: "training-experiment"
    display_name: "Daily training"
    compute: "gpu"                    # references a compute entry
    workspace: "prod"                 # references a workspace entry
    description: "Run the training pipeline on GPU"
    schedule:                         # inline schedule (or reference a named one)
      cron:
        expression: "0 8 * * 1-5"
        time_zone: "UTC"
```

#### Pipeline filter options

The `pipeline` section supports all Kedro pipeline filters:

| Field | Description |
|---|---|
| `pipeline_name` | Kedro pipeline name (default: `__default__`) |
| `from_nodes` | Start from these nodes |
| `to_nodes` | Run up to these nodes |
| `node_names` | Run only these specific nodes |
| `from_inputs` | Start from nodes that produce these datasets |
| `to_outputs` | Run up to nodes that produce these datasets |
| `node_namespaces` | Filter by namespace |
| `tags` | Filter by tag |

## CLI commands

All commands are available under `kedro azureml`:

### `kedro azureml init`

```text
kedro azureml init
```

Creates `conf/base/azureml.yml` (with placeholder values) and `.amlignore`.

### `kedro azureml compile`

```text
kedro azureml compile -j JOB_NAME [-o OUTPUT] [--params JSON] [--env-var KEY=VALUE] [--aml-env ENV] [--load-versions KEY:VERSION]
```

Compiles named job(s) into Azure ML pipeline YAML definitions. Accepts multiple `-j` flags.

| Flag | Description |
|---|---|
| `-j JOB_NAME` | Job name from the `jobs` config section (required, repeatable) |
| `-o OUTPUT` | Output YAML file path (default: `pipeline.yaml`) |
| `--aml-env ENV` | Override the Azure ML environment |
| `--params JSON` | Runtime parameters as a JSON string |
| `--env-var KEY=VALUE` | Inject environment variables into steps (repeatable) |
| `--load-versions KEY:VERSION` | Dataset version overrides |

### `kedro azureml run`

```text
kedro azureml run -j JOB_NAME [--dry-run] [--wait-for-completion] [-w WORKSPACE] [--aml-env ENV] [--params JSON] [--env-var KEY=VALUE] [--load-versions KEY:VERSION] [--on-job-scheduled MODULE:FUNC]
```

Runs named job(s) immediately on Azure ML, ignoring any configured schedule.

| Flag | Description |
|---|---|
| `-j JOB_NAME` | Job name from the `jobs` config section (required, repeatable) |
| `--dry-run` | Preview without running |
| `--wait-for-completion` | Block until the run completes |
| `-w WORKSPACE` | Override workspace for all jobs in this batch |
| `--aml-env ENV` | Override the Azure ML environment |
| `--params JSON` | Runtime parameters as a JSON string |
| `--env-var KEY=VALUE` | Inject environment variables into steps (repeatable) |
| `--load-versions KEY:VERSION` | Dataset version overrides |
| `--on-job-scheduled MODULE:FUNC` | Callback invoked after each job is submitted |

### `kedro azureml schedule`

```text
kedro azureml schedule -j JOB_NAME [--dry-run] [-w WORKSPACE] [--aml-env ENV] [--params JSON] [--env-var KEY=VALUE] [--load-versions KEY:VERSION]
```

Creates or updates persistent Azure ML schedules for named job(s). Every selected job must have a `schedule` configured in `azureml.yml`.

| Flag | Description |
|---|---|
| `-j JOB_NAME` | Job name from the `jobs` config section (required, repeatable) |
| `--dry-run` | Preview without creating schedules |
| `-w WORKSPACE` | Override workspace for all jobs in this batch |
| `--aml-env ENV` | Override the Azure ML environment |
| `--params JSON` | Runtime parameters as a JSON string |
| `--env-var KEY=VALUE` | Inject environment variables into steps (repeatable) |
| `--load-versions KEY:VERSION` | Dataset version overrides |

### `kedro azureml execute` (internal)

Used internally by Azure ML pipeline steps to run individual Kedro nodes. Not intended for direct use.

## Scheduling

### Inline schedule

Attach a schedule directly to a job:

```yaml
jobs:
  nightly:
    pipeline:
      pipeline_name: "__default__"
    schedule:
      cron:
        expression: "0 2 * * *"
        time_zone: "UTC"
```

### Recurrence schedule

```yaml
jobs:
  weekly:
    pipeline:
      pipeline_name: "__default__"
    schedule:
      recurrence:
        frequency: "week"
        interval: 1
        schedule:
          week_days: ["Monday", "Wednesday", "Friday"]
          hours: [9]
          minutes: [0]
```

### Reusable schedule definitions

Define schedules once and reference them by name:

```yaml
schedules:
  business_hours:
    cron:
      expression: "0 9 * * 1-5"
      time_zone: "Europe/London"

jobs:
  training:
    pipeline:
      pipeline_name: "__default__"
    schedule: "business_hours"
```

## Data assets

### AzureMLAssetDataset

Use `AzureMLAssetDataset` in your Kedro catalog to read and write Azure ML data assets (`uri_file` or `uri_folder`):

```yaml
# conf/base/catalog.yml
model_input:
  type: kedro_azureml_pipeline.datasets.AzureMLAssetDataset
  azureml_dataset: "my-dataset"
  version_type: "uri_folder"
  dataset:
    type: pandas.ParquetDataset
    filepath: "data.parquet"
```

The `AzureMLLocalRunHook` (registered in `settings.py`) automatically resolves data asset paths for local runs. During remote execution on Azure ML, the runner handles path injection via `--az-input` and `--az-output` flags.

## Distributed training

Decorate Kedro node functions with `@distributed_job` to run them as distributed training steps:

```python
from kedro_azureml_pipeline.distributed import distributed_job, Framework

@distributed_job(framework=Framework.PyTorch, num_nodes=4)
def train_model(data):
    # Your distributed training code
    ...
```

Supported frameworks:

| Framework | Value |
|---|---|
| PyTorch | `Framework.PyTorch` |
| TensorFlow | `Framework.TensorFlow` |
| MPI | `Framework.MPI` |

The `num_nodes` and optional `processes_per_node` parameters control the distributed configuration.

## MLflow integration

When using [kedro-mlflow](https://kedro-mlflow.readthedocs.io/), Kedro AzureML Pipeline includes an `MlflowAzureMLHook` that coordinates experiment tracking:

- Sets the MLflow tracking URI to the Azure ML workspace
- Tags each child run with the Kedro node name
- Routes logs to the correct experiment

The hook activates automatically when the `KEDRO_AZUREML_MLFLOW_ENABLED` environment variable is set to `"1"` (injected by the pipeline generator during remote execution).

## Multiple workspaces

Define additional workspaces and reference them per-job:

```yaml
workspace:
  __default__:
    subscription_id: "..."
    resource_group: "rg-dev"
    name: "aml-dev"
  staging:
    subscription_id: "..."
    resource_group: "rg-staging"
    name: "aml-staging"

jobs:
  deploy:
    pipeline:
      pipeline_name: "deployment"
    workspace: "staging"
```

You can also override the workspace at run time:

```bash
kedro azureml run -j training -w staging
```

## Environment variables

Inject environment variables into Azure ML pipeline steps:

```bash
kedro azureml run -j training --env-var API_KEY=secret --env-var DEBUG=1
```

## Next steps

- [Getting Started](getting-started.md) for installation and first submission
- [API Reference](api-reference.md) for full module and class documentation
- [FAQ & Troubleshooting](faq.md) for common questions and issue resolution
