# Configuration Reference

All plugin settings live in `conf/<env>/azureml.yml`. The file is parsed into [`KedroAzureMLConfig`][kedro_azureml_pipeline.config.KedroAzureMLConfig]. For dataset configuration in `catalog.yml`, see the [Datasets reference](datasets.md).

## Top-level structure

```yaml
workspace:             # required
compute:               # required
execution:             # optional
schedules:             # optional
notifications:         # optional
jobs:                  # optional
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

Jobs reference a workspace by name via their `workspace` field. The `__default__` is used when no workspace is specified. See [Configure multiple workspaces](../how-to/configure-multiple-workspaces.md) for a walkthrough.

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
| `cluster_name` | string | on `__default__` | Name of the Azure ML compute cluster. Tag entries inherit it from `__default__` when omitted |
| `instance_type` | string | no | Azure ML instance type to run steps under. Kubernetes compute targets only |

Jobs reference a compute entry by name via their `compute` field.

### Kubernetes compute targets

When `cluster_name` points at an attached Kubernetes compute target (AKS or Azure Arc), `instance_type` selects the `InstanceType` custom resource the step runs under. Instance types are defined on the cluster by its administrator; the plugin passes the name through without validating it.

When `instance_type` is omitted, Azure ML runs the step under `defaultinstancetype`, whose stock definition limits each step to 2 CPU cores, 2 GiB of memory, and no GPU. Set an instance type for any workload that needs more than that ceiling, and for every GPU workload.

The field has no effect on AmlCompute clusters; Azure ML ignores it there.

### Tag-based routing

Kedro node tags can route nodes to specific compute clusters. When a node has a tag that matches a named compute entry, that entry is merged with `__default__` field by field:

```yaml
compute:
  __default__:
    cluster_name: "k8s-compute"
  gpu:
    instance_type: "gpu-large"
  cpu-heavy:
    cluster_name: "other-compute"
```

A node tagged `gpu` in your Kedro pipeline will run on `k8s-compute` under the `gpu-large` instance type. Nodes without a matching tag fall back to `__default__`. Fields from the tagged entry override `__default__` fields, and omitted fields are inherited: the `cpu-heavy` entry above inherits any `instance_type` set on `__default__`, so set it explicitly when the target cluster defines different instance types.

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
| `working_directory` | `null` | Working directory inside the compute container. Set this when your Azure ML environment expects code at a specific path (e.g. `/home/kedro`). When `null`, Azure ML uses its default working directory. |

The combination of `environment` and `code_directory` determines the deployment flow. When `code_directory` is set (e.g. `"."`), the plugin uploads a snapshot of your project and runs it inside the environment (**code flow**). When `code_directory` is `null`, the plugin expects the code to already be baked into the Docker image referenced by `environment` (**image flow**). See [Deploy from CI/CD](../how-to/deploy-from-cicd.md) for guidance on choosing between the two.

In the code flow, `kedro azureml run` and `kedro azureml schedule` stage the snapshot once per invocation and register it once per workspace:

1. The files that the ignore file of `code_directory` keeps (`.amlignore` first, else `.gitignore`) are copied into a temporary directory. The selection is the Azure ML SDK's own, so a whitelist `.amlignore` behaves exactly as it does for a direct upload.
2. That directory is registered as one anonymous code asset, the same content-addressed kind the SDK creates for snapshots itself. An upload whose content hash already exists in the workspace's storage is skipped and resolves to the existing asset, so unchanged code creates nothing new.
3. Every step of every job in the batch references that asset instead of a local path.

Without staging, the SDK walks and hashes the whole `code_directory` once per step, which for a large working tree (a virtual environment, data, git objects) dominates submission time. `kedro azureml compile` keeps the configured path in its output and neither stages nor registers, so it needs no credentials.

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

Each schedule entry has exactly one of `cron` or `recurrence`. See [Schedule pipelines](../how-to/schedule-pipelines.md) for end-to-end setup.

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

## `notifications`

Reusable named notification definitions. Jobs reference them by name, and the plugin then posts one `start`, one `success`, and one `failure` message per run of the job, whoever submitted it and however many steps it has, to a webhook or through the Slack API.

```yaml
notifications:
  alerts:
    webhook_env: SLACK_WEBHOOK_URL
    events: [start, success, failure]
    payload: my_project.notifications:build_payload
    wait_timeout: 900
  threaded:
    token_env: SLACK_BOT_TOKEN
    channel: C0123456789
    events: [start, success, failure]
    payload: my_project.notifications:build_payload
```

| Field | Default | Description |
|---|---|---|
| `webhook_env` | `null` | Name of the environment variable, inside the step, that holds the webhook URL. The URL itself never appears in configuration |
| `token_env` | `null` | Name of the environment variable, inside the step, that holds the Slack bot token. Set together with `channel` |
| `channel` | `null` | Slack channel ID the API posts to. Set together with `token_env` |
| `events` | required | Events to report: any non-empty subset of `start`, `success`, `failure`, `warning`, `recovered` |
| `payload` | `null` | `module.path:function_name` reference to a payload builder called with a [`NotificationEvent`][kedro_azureml_pipeline.hooks.NotificationEvent]; `null` posts a plain `{"text": ...}` payload |
| `wait_timeout` | `1800` | Seconds the outcome step waits for the job's other leaf steps before posting an outcome-unknown message instead of `success` |
| `warning_repeat_hours` | `24` | While a job stays degraded, hours between reminders of the same outage, measured between run start times |
| `warning_repeat_tolerance_minutes` | `15` | How many minutes early a reminder may come |

The field is named `events` rather than `on` because YAML 1.1 reads a bare `on` key as the boolean true.

A definition names at least one transport: `webhook_env`, or `token_env` with `channel`. When it names both, a step posts through the API when the token is present in its environment and through the webhook otherwise. The API transport threads the outcome messages under the run's `start` message and also sends them to the channel; see [Notify on run outcomes](../how-to/notify-on-run-outcomes.md#post-through-the-slack-api) for what that requires.

Two more rules are checked when the configuration loads or the job compiles:

- When the referencing job declares `limits.timeout`, `wait_timeout` must be **below** it. The outcome step's wait counts against its own step budget, and a step cancelled mid-wait posts nothing.
- A job that enables `success` on a pipeline with **more than one leaf node** must declare an `experiment_name` and run with the plugin's `mlflow` extra installed. The outcome step identifies its sibling leaves through the MLflow run tags the [MLflow integration](../how-to/use-mlflow.md) writes, and only an experiment name activates that integration.

See [Notify on run outcomes](../how-to/notify-on-run-outcomes.md) for the end-to-end setup and the exact once-per-job rules.

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
    params:
      lookback_days: 30
    limits:
      timeout: 3600
```

| Field | Default | Description |
|---|---|---|
| `pipeline` | required | Pipeline selection and filter options (see below) |
| `workspace` | `null` | Named workspace entry; falls back to `__default__` |
| `experiment_name` | `null` | Azure ML experiment name |
| `display_name` | `null` | Display name shown in Azure ML Studio |
| `compute` | `null` | Named compute entry; falls back to `__default__` |
| `schedule` | `null` | Inline `ScheduleConfig`, named schedule string, a **list** of either (one trigger deployed per entry), or `null` for ad-hoc |
| `params` | `null` | Job-scoped runtime parameters merged into the pipeline on `compile`, `run`, and `schedule` (see below) |
| `limits` | `null` | Run-duration limits applied to every step in the job (see below) |
| `description` | `null` | Human-readable job description |
| `notifications` | `null` | Name of a [`notifications`](#notifications) definition whose webhook receives this job's run events |

### `params`

Optional job-scoped runtime parameters, equivalent to passing `--params` for that job but stored in config so every `compile`, `run`, and `schedule` of the job picks them up. When a value is also given on the command line, the **CLI `--params` value wins** for that key; remaining job-level keys are kept. This lets a job carry stable defaults while still allowing one-off overrides at submission time.

```yaml
jobs:
  training:
    pipeline:
      pipeline_name: "__default__"
    params:
      lookback_days: 30
      model: "lgbm"
```

### Job factories

A `jobs` key that contains `{placeholder}` markers is a **job factory**: a templated job entry, mirroring a Kedro dataset factory. By default the jobs are derived from your **pipeline namespaces**, the same way a dataset factory's concrete datasets are determined by pipeline node references. You write a few factory patterns, and the concrete jobs come from the namespaces of each factory's pipeline. No target list is required:

```yaml
jobs:
  # one job per namespace of the `inference` pipeline
  "{region}-{model}-inference":
    schedule: nightly
    pipeline:
      pipeline_name: "inference"
      node_namespaces: ["{region}.{model}"]
  # a more-specific pattern overrides the schedule for one region
  "america-{model}-inference":
    schedule: "hourly"
    pipeline:
      pipeline_name: "inference"
      node_namespaces: ["{region}.{model}"]
  # literal (non-factory) jobs are kept verbatim and take precedence
  snapshot:
    pipeline: {pipeline_name: "snapshot"}
```

**Bindings come from the pipeline.** For each factory, the `node_namespaces` template defines the placeholder names and their namespace depth. The plugin enumerates the distinct namespaces of `pipeline_name` at that depth and binds the placeholders positionally (so the namespace `europe.lgbm` binds `region=europe, model=lgbm`). One job is produced per binding. Adding a variant to your pipelines makes its job appear with no `azureml.yml` edit. A factory name placeholder that is absent from its `node_namespaces` template is a configuration error. When `node_namespaces` holds more than one entry, only the first is the binding axis; the rest are not used for derivation but still render per job as ordinary runtime namespace filters.

**Resolution is forward-only.** Job names are produced only by rendering placeholders into a pattern; names are never parsed back. When more than one pattern renders the same name, the **most-specific** one (most literal, non-placeholder characters) supplies the config, so per-region variation such as a different schedule is expressed by a more-specific pattern rather than an override table. Literal (non-factory) jobs take precedence over any pattern.

`{placeholder}` (factory) and `${...}` (OmegaConf) use different syntax and coexist. The namespace alone identifies the job, so no `tags` filter is needed. Job names use the namespace form of each placeholder verbatim (so `europe.lgbm` yields `europe-lgbm-inference`).

- **`kedro azureml run -j <name>`** renders all bindings (overlaying literal jobs) and looks the requested name up; an unknown name is an error listing the available jobs.
- **`kedro azureml resolve-patterns`** lists every derived job (see the [CLI reference](cli.md)), which is how you discover the names to pass to `-j`.

There is no separate target list or provider key: the jobs are always derived from the pipeline namespaces, so adding a variant to your pipelines yields its job with no config edit.

For the dataset-factory analogy and why resolution is forward-only, see [Job Factories](../explanation/job-factories.md); for a step-by-step recipe, see [Define jobs with factories](../how-to/define-job-factories.md).

### `limits`

Optional run-duration limits applied to every command step in the job. Maps to [`azure.ai.ml.entities.CommandJobLimits`](https://learn.microsoft.com/en-us/python/api/azure-ai-ml/azure.ai.ml.entities.commandjoblimits).

```yaml
limits:
  timeout: 3600
```

| Field | Default | Description |
|---|---|---|
| `timeout` | required | Maximum run duration in seconds, after which Azure ML cancels the step (must be >= 1) |

The timeout is a hang guard rather than an expected duration. When it is reached, Azure ML cancels the step and releases the compute instances it was holding, so a wedged step does not occupy a cluster indefinitely. Set it above your slowest realistic run, not at it.

!!! warning "There is no retry setting"

    Azure ML declares `RetrySettings` for parallel and sweep jobs only. This plugin compiles every Kedro node into a **command** step, so a retry setting would be accepted by the SDK as an unknown field and then ignored by the service. `limits` is offered because the command-step contract acts on it; retries are not available and a failed step is not re-run.

### `pipeline` filter options

These fields correspond to the parameters of Kedro's `Pipeline.filter()` method.

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

The following environment variables are set automatically by the plugin during remote execution. They are reserved and should not be set directly.

| Variable | Set by | Description |
|---|---|---|
| `KEDRO_AZUREML_MLFLOW_ENABLED` | Pipeline generator | Set to `"1"` on each step during remote execution to activate [MLflow integration](../how-to/use-mlflow.md) |
| `KEDRO_AZUREML_NOTIFY` | Pipeline generator | JSON of the job's resolved [`notifications`](#notifications) definition plus job name, display name, and pipeline name, on every step of a job that references one |
| `KEDRO_AZUREML_NOTIFY_START` | Pipeline generator | Set to `"1"` on the one root step that posts `start` |
| `KEDRO_AZUREML_NOTIFY_OUTCOME` | Pipeline generator | Set to `"1"` on the one leaf step that posts the outcome |
| `KEDRO_AZUREML_NOTIFY_SIBLINGS` | Pipeline generator | Comma-separated names of the other leaf nodes the outcome step waits for |
