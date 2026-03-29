# How to Configure Multiple Workspaces

This guide shows how to define multiple Azure ML workspaces in a single configuration and target different workspaces per job or at run time.

## Prerequisites

- The Kedro AzureML Pipeline plugin configured with at least one workspace (see [Getting Started](../tutorials/getting-started.md))
- Access to the additional Azure ML workspaces you want to configure

## Define additional workspaces

Add named workspace entries to `conf/base/azureml.yml`. The `__default__` entry is required and is used when no workspace is specified:

```yaml
workspace:
  __default__:
    subscription_id: "00000000-0000-0000-0000-000000000000"
    resource_group: "rg-dev"
    name: "aml-dev"
  staging:
    subscription_id: "11111111-1111-1111-1111-111111111111"
    resource_group: "rg-staging"
    name: "aml-staging"
  prod:
    subscription_id: "22222222-2222-2222-2222-222222222222"
    resource_group: "rg-prod"
    name: "aml-prod"
```

## Assign a workspace to a job

Reference a named workspace from the job definition:

```yaml
jobs:
  training:
    pipeline:
      pipeline_name: "__default__"
    workspace: "staging"

  production_deploy:
    pipeline:
      pipeline_name: "deployment"
    workspace: "prod"
```

Jobs without a `workspace` key fall back to `__default__`.

## Override the workspace at run time

Use `-w` to target a different workspace for the current invocation without editing `azureml.yml`:

```bash
kedro azureml run -j training -w prod
```

The `-w` flag overrides the workspace for all jobs in that batch. It does not modify `azureml.yml`.

## Combine with environment-specific config

Use Kedro environments to maintain separate workspace configurations per environment:

```text
conf/
  base/
    azureml.yml      # shared defaults
  prod/
    azureml.yml      # production workspace overrides
```

Run with the production environment:

```bash
kedro azureml run -j training --env prod
```

## See also

- [Configuration reference](../reference/configuration.md#workspace) - full workspace field documentation
- [CLI reference](../reference/cli.md#kedro-azureml-run) - `-w` flag and other run options
