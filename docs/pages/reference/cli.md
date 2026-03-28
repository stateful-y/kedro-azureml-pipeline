# CLI Reference

All commands are available under `kedro azureml`. Run `kedro azureml --help` to list them.

---

## `kedro azureml init`

```text
kedro azureml init
```

Initializes the plugin in the current Kedro project. Creates:

- `conf/base/azureml.yml` - configuration file with placeholder values
- `.amlignore` - file exclusion list for code upload

No flags.

---

## `kedro azureml compile`

```text
kedro azureml compile -j JOB_NAME [options]
```

Compiles named job(s) into Azure ML pipeline YAML definitions without submitting them.

| Flag | Description |
|---|---|
| `-j JOB_NAME` | Job name from `jobs` in `azureml.yml`. Required. Repeatable for multiple jobs. |
| `-o OUTPUT` | Output YAML file path (default: `pipeline.yaml`) |
| `--aml-env ENV` | Override the Azure ML environment for this invocation |
| `--params JSON` | Runtime parameters as a JSON string (e.g. `'{"key": "value"}'`) |
| `--env-var KEY=VALUE` | Inject an environment variable into pipeline steps. Repeatable. |
| `--load-versions KEY:VERSION` | Pin a dataset to a specific Kedro-versioned version. Repeatable. |

---

## `kedro azureml run`

```text
kedro azureml run -j JOB_NAME [options]
```

Submits named job(s) to Azure ML managed compute immediately, ignoring any configured schedule.

| Flag | Description |
|---|---|
| `-j JOB_NAME` | Job name from `jobs` in `azureml.yml`. Required. Repeatable for multiple jobs. |
| `--dry-run` | Preview the pipeline definition without submitting to Azure ML |
| `--wait-for-completion` | Block the terminal until the run finishes |
| `-w WORKSPACE` | Override the workspace for all jobs in this batch |
| `--aml-env ENV` | Override the Azure ML environment for this invocation |
| `--params JSON` | Runtime parameters as a JSON string |
| `--env-var KEY=VALUE` | Inject an environment variable into pipeline steps. Repeatable. |
| `--load-versions KEY:VERSION` | Pin a dataset to a specific Kedro-versioned version. Repeatable. |
| `--on-job-scheduled MODULE:FUNC` | Callback invoked after each job is submitted (e.g. `mymodule:notify`) |

---

## `kedro azureml schedule`

```text
kedro azureml schedule -j JOB_NAME [options]
```

Creates or updates persistent Azure ML schedules for named job(s). Every selected job must have a `schedule` configured in `azureml.yml`.

| Flag | Description |
|---|---|
| `-j JOB_NAME` | Job name from `jobs` in `azureml.yml`. Required. Repeatable for multiple jobs. |
| `--dry-run` | Preview the schedule definition without creating it in Azure ML |
| `-w WORKSPACE` | Override the workspace for all jobs in this batch |
| `--aml-env ENV` | Override the Azure ML environment for this invocation |
| `--params JSON` | Runtime parameters as a JSON string |
| `--env-var KEY=VALUE` | Inject an environment variable into pipeline steps. Repeatable. |
| `--load-versions KEY:VERSION` | Pin a dataset to a specific Kedro-versioned version. Repeatable. |

---

## `kedro azureml execute`

Used internally by Azure ML pipeline steps to run individual Kedro nodes on compute. Not intended for direct use.

---

## Common flags

The following flags are accepted by `compile`, `run`, and `schedule`:

| Flag | Description |
|---|---|
| `--params JSON` | Runtime parameters as a JSON string |
| `--env-var KEY=VALUE` | Inject environment variables into pipeline steps (repeatable) |
| `--load-versions KEY:VERSION` | Dataset version overrides (repeatable) |
| `--aml-env ENV` | Override the Azure ML environment |
