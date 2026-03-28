# Configuration Reference

All plugin settings live in `conf/<env>/azureml.yml`. The file is parsed into `KedroAzureMLConfig`.

## Top-level structure

```yaml
workspace:    # required
compute:      # required
execution:    # optional
schedules:    # optional
jobs:         # optional
```

---

## `workspace`

Named Azure ML workspace definitions. A `__default__` entry is required.

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

Each workspace entry (`WorkspaceConfig`) has the following fields:

| Field | Type | Required | Description |
|---|---|---|---|
| `subscription_id` | string | yes | Azure subscription ID |
| `resource_group` | string | yes | Azure resource group name |
| `name` | string | yes | Azure ML workspace name |

Jobs reference a workspace by name via their `workspace` field. The `__default__` is used when no workspace is specified.

---

## `compute`

Named compute cluster definitions. A `__default__` entry is required.

```yaml
compute:
  __default__:
    cluster_name: "cpu-cluster"
  gpu:
    cluster_name: "gpu-cluster"
```

Each compute entry (`ClusterConfig`) has the following fields:

| Field | Type | Required | Description |
|---|---|---|---|
| `cluster_name` | string | yes | Name of the Azure ML compute cluster |

Jobs reference a compute entry by name via their `compute` field.

---

## `execution`

Code packaging and container settings. All fields are optional.

```yaml
execution:
  environment: "my-env@latest"
  code_directory: "."
  working_directory: /home/kedro
```

| Field | Default | Description |
|---|---|---|
| `environment` | `null` | Azure ML environment name (e.g. `my-env@latest` or `my-env:3`) |
| `code_directory` | `null` | Local directory to upload as a code snapshot; `null` disables code upload |
| `working_directory` | `null` | Working directory inside the compute container |

---

## `schedules`

Reusable named schedule definitions. Jobs reference them by name.

```yaml
schedules:
  business_hours:
    cron:
      expression: "0 9 * * 1-5"
      time_zone: "Europe/London"
```

Each schedule entry has exactly one of `cron` or `recurrence`.

### `cron`

| Field | Default | Description |
|---|---|---|
| `expression` | required | Cron expression (e.g. `"0 2 * * *"`) |
| `time_zone` | `"UTC"` | IANA time zone name (e.g. `"Europe/London"`) |
| `start_time` | `null` | ISO 8601 start time |
| `end_time` | `null` | ISO 8601 end time |

### `recurrence`

| Field | Default | Description |
|---|---|---|
| `frequency` | required | Recurrence unit: `"minute"`, `"hour"`, `"day"`, `"week"`, or `"month"` |
| `interval` | required | Number of frequency units between runs |
| `time_zone` | `"UTC"` | IANA time zone name |
| `start_time` | `null` | ISO 8601 start time |
| `end_time` | `null` | ISO 8601 end time |
| `schedule.hours` | `null` | Hours of the day to trigger |
| `schedule.minutes` | `null` | Minutes of the hour to trigger |
| `schedule.week_days` | `null` | Days of the week to trigger (e.g. `["Monday", "Friday"]`) |

---

## `jobs`

Named job definitions. Each job maps a Kedro pipeline to an Azure ML pipeline submission.

```yaml
jobs:
  training:
    pipeline:
      pipeline_name: "__default__"
      tags: ["training"]
    experiment_name: "training-experiment"
    display_name: "Daily training"
    compute: "gpu"
    workspace: "prod"
    description: "Run the training pipeline on GPU cluster"
    schedule: "business_hours"
```

| Field | Default | Description |
|---|---|---|
| `pipeline` | required | Pipeline selection and filter options (see below) |
| `workspace` | `null` | Named workspace entry; falls back to `__default__` |
| `experiment_name` | `null` | Azure ML experiment name |
| `display_name` | `null` | Display name shown in Azure ML Studio |
| `compute` | `null` | Named compute entry; falls back to `__default__` |
| `schedule` | `null` | Inline `ScheduleConfig`, named schedule string, or `null` for ad-hoc |
| `description` | `null` | Human-readable job description |

### `pipeline` filter options

| Field | Default | Description |
|---|---|---|
| `pipeline_name` | `"__default__"` | Kedro pipeline name |
| `from_nodes` | `null` | Start from these nodes |
| `to_nodes` | `null` | Run up to these nodes |
| `node_names` | `null` | Run only these specific nodes |
| `from_inputs` | `null` | Start from nodes that produce these datasets |
| `to_outputs` | `null` | Run up to nodes that produce these datasets |
| `node_namespaces` | `null` | Filter by namespace |
| `tags` | `null` | Filter by tag |

---

## Environment variables

Environment variables can be injected into pipeline steps at run time using `--env-var KEY=VALUE` on any CLI command that supports it.

| Variable | Set by | Description |
|---|---|---|
| `KEDRO_AZUREML_MLFLOW_ENABLED` | Pipeline generator | Set to `"1"` on each step during remote execution to activate [MLflow integration](../how-to/use-mlflow.md) |
