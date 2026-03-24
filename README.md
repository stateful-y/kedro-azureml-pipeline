<p align="center">
  <picture>
    <source media="(prefers-color-scheme: light)" srcset="https://raw.githubusercontent.com/stateful-y/kedro-azureml-pipeline/main/docs/assets/logo_light.png">
    <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/stateful-y/kedro-azureml-pipeline/main/docs/assets/logo_dark.png">
    <img src="https://raw.githubusercontent.com/stateful-y/kedro-azureml-pipeline/main/docs/assets/logo_light.png" alt="Kedro AzureML Pipeline">
  </picture>
</p>

[![Python Version](https://img.shields.io/pypi/pyversions/kedro-azureml-pipeline)](https://pypi.org/project/kedro-azureml-pipeline/)
[![License](https://img.shields.io/github/license/stateful-y/kedro-azureml-pipeline)](https://github.com/stateful-y/kedro-azureml-pipeline/blob/main/LICENSE)
[![PyPI Version](https://img.shields.io/pypi/v/kedro-azureml-pipeline)](https://pypi.org/project/kedro-azureml-pipeline/)
[![codecov](https://codecov.io/gh/stateful-y/kedro-azureml-pipeline/branch/main/graph/badge.svg)](https://codecov.io/gh/stateful-y/kedro-azureml-pipeline)

> [!NOTE]
> This project is a fork of [kedro-azureml](https://github.com/getindata/kedro-azureml) originally created by [Marcin Zablocki](https://github.com/marrrcin) at [GetInData](https://github.com/getindata). It has been forked to continue active development and add new features.

## What is Kedro AzureML Pipeline?

Kedro AzureML Pipeline is a plugin that enables running [Kedro](https://kedro.org/) pipelines on [Azure ML Pipelines](https://learn.microsoft.com/en-us/azure/machine-learning/concept-ml-pipelines). It translates your Kedro pipeline into an Azure ML pipeline job where each Kedro node becomes a separate step.

Two deployment workflows are supported, both backed by Azure ML Environments:

- **Code upload**: only dependencies live in the Docker image; source code is uploaded at runtime (fast iteration for data scientists)
- **Docker image**: code is baked into the image (stable, repeatable workflows for MLOps)

### Key features

| Feature | Description |
|---|---|
| **Pipeline translation** | Automatic Kedro node → Azure ML step mapping via the `compile`, `run`, and `schedule` CLI commands |
| **Named jobs** | Define multiple jobs in `azureml.yml`, each targeting a different pipeline, compute, or workspace |
| **Scheduling** | Attach cron or recurrence schedules to jobs for recurring Azure ML pipeline runs |
| **Data assets** | `AzureMLAssetDataset` for reading/writing Azure ML `uri_file` and `uri_folder` data assets |
| **Distributed training** | `@distributed_job` decorator with PyTorch, TensorFlow, and MPI backends |
| **MLflow integration** | Optional hook that wires Kedro-MLFlow to log under the correct Azure ML experiment |
| **Multiple workspaces** | Named workspace definitions with a `__default__` fallback |

## Installation

```bash
pip install kedro-azureml-pipeline
```

or with [uv](https://docs.astral.sh/uv/):

```bash
uv add kedro-azureml-pipeline
```

## Quick start

### 1. Initialize configuration

```bash
kedro azureml init
```

This creates `conf/base/azureml.yml` with placeholder values and an `.amlignore` file.

### 2. Review the generated configuration

Open `conf/base/azureml.yml` and fill in your Azure details:

```yaml
workspace:
  __default__:
    subscription_id: "<subscription_id>"
    resource_group: "<resource_group>"
    name: "<workspace_name>"

compute:
  __default__:
    cluster_name: "<cluster_name>"

execution:
  environment: "<environment>"
  code_directory: "."
```

### 3. Define a job and submit

Add a job to `azureml.yml`:

```yaml
jobs:
  training:
    pipeline:
      pipeline_name: "__default__"
    experiment_name: "my-experiment"
```

Then submit it:

```bash
kedro azureml submit -j training
```

Use `--dry-run` to preview without submitting, or `--wait-for-completion` to block until the run finishes.

### 4. Compile to YAML (optional)

Export the Azure ML pipeline definition for inspection or CI:

```bash
kedro azureml compile -j training -o pipeline.yaml
```

## Documentation

Full documentation is available at [https://kedro-azureml-pipeline.readthedocs.io/](https://kedro-azureml-pipeline.readthedocs.io/).

## Contributing

We welcome contributions, feedback, and questions:

- **Report issues or request features**: [GitHub Issues](https://github.com/stateful-y/kedro-azureml-pipeline/issues)
- **Contributing guide**: [CONTRIBUTING.md](https://github.com/stateful-y/kedro-azureml-pipeline/blob/main/CONTRIBUTING.md)
- **Discussions**: [GitHub Discussions](https://github.com/stateful-y/kedro-azureml-pipeline/discussions)

## License

This project is licensed under the terms of the [Apache-2.0 License](https://github.com/stateful-y/kedro-azureml-pipeline/blob/main/LICENSE).

## Acknowledgements

This project is a fork of [kedro-azureml](https://github.com/getindata/kedro-azureml), originally developed by [GetInData](https://github.com/getindata). We are grateful for their work in creating the initial plugin that bridges Kedro and Azure ML Pipelines. We have continued development to add new features, improve documentation, and maintain the project under the `kedro-azureml-pipeline` package name.

We would also like to thank [Evolta Technologies](https://www.evolta-technologies.com/) for their support to the project.

<br>

<p align="center">
  <a href="https://www.evolta-technologies.com/">
    <img src="docs/assets/evolta_logo.png" alt="Evolta Technologies" width="400">
  </a>
</p>

<br>

This project is maintained by [stateful-y](https://stateful-y.io), an ML consultancy specializing in MLOps and data science & engineering. If you're interested in collaborating or learning more about our services, please visit our website.

<p align="center">
  <a href="https://stateful-y.io">
    <img src="docs/assets/made_by_stateful-y.png" alt="Made by stateful-y" width="200">
  </a>
</p>
