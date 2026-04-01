# How to Schedule Pipelines

This guide shows how to configure recurring schedules for Kedro AzureML Pipeline jobs using cron expressions, recurrence rules, or reusable schedule definitions.

## Prerequisites

- A job defined under `jobs:` in `conf/base/azureml.yml` (see [Getting Started](../tutorials/getting-started.md))
- The target Azure ML workspace and compute configured
- Azure credentials available (`az login` or service principal)
- Familiarity with [cron expressions](https://en.wikipedia.org/wiki/Cron#Cron_expression) (for cron schedules)

## Attach a cron schedule to a job

Add a `schedule.cron` block inside the job definition:

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

The `time_zone` field accepts [IANA time zone names](https://www.iana.org/time-zones) (e.g. `"Europe/London"`) or `"UTC"`.

Create or update the schedule in Azure ML:

```bash
kedro azureml schedule -j nightly
```

## Use a recurrence schedule

Recurrence schedules let you express intervals, days, hours, and minutes without cron syntax:

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

Valid `frequency` values are `"minute"`, `"hour"`, `"day"`, `"week"`, and `"month"`.

## Share a schedule across multiple jobs

Define schedules once under `schedules:` and reference them by name:

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

  validation:
    pipeline:
      pipeline_name: "validation"
    schedule: "business_hours"
```

## Preview without creating

Use `--dry-run` to inspect what will be created without calling Azure ML:

```bash
kedro azureml schedule -j nightly --dry-run
```

## Schedule multiple jobs at once

Pass `-j` multiple times to schedule several jobs together:

```bash
kedro azureml schedule -j training -j validation
```

## Override workspace at run time

```bash
kedro azureml schedule -j nightly -w prod
```

The `-w` flag overrides the workspace for the current invocation. It does not modify `azureml.yml`.

## See also

- [Configuration reference](../reference/configuration.md#jobs) for the full `schedule` field documentation
- [CLI reference](../reference/cli.md#kedro-azureml-schedule) for all `kedro azureml schedule` flags
- [Troubleshoot](troubleshoot.md#schedule-not-triggering) if your schedule is not triggering
- [Deploy from CI/CD](deploy-from-cicd.md) for automating schedule creation in pipelines
