# Introduction

Kedro AzureML Pipeline is a plugin that seamlessly connects your **Kedro** data science project to **Azure ML Pipelines'** orchestration engine. With minimal setup, you can run, schedule, and monitor Kedro pipelines on Azure ML, taking advantage of its managed compute, experiment tracking, and cloud‑native infrastructure without altering your existing codebase.

## What is Kedro?

[Kedro](https://kedro.readthedocs.io/) is a Python framework for building reproducible, maintainable, and modular data science code. It enforces best practices such as separation of concerns, configuration management, and a data catalog, ensuring that pipelines are production‑ready from the start.

## What is Azure ML Pipelines?

[Azure ML Pipelines](https://learn.microsoft.com/en-us/azure/machine-learning/concept-ml-pipelines) is a cloud service for building and orchestrating machine learning workflows. It provides:

- **Managed compute:** Provision and auto‑scale compute clusters on demand.
- **Experiment tracking:** Track metrics, parameters, and artifacts across runs.
- **Pipeline orchestration:** Define multi‑step workflows with data dependencies.
- **Scheduling:** Configure recurring and event‑driven pipeline triggers.
- **Enterprise integration:** Built‑in authentication, networking, and compliance features.

Azure ML Pipelines scales from experimentation to production, with native support for MLflow, distributed training, and CI/CD integration.

## Why Kedro‑AzureML‑Pipeline?

Kedro and Azure ML Pipelines are complementary. Kedro provides a robust developer experience for building pipelines—modular, testable, and backed by strong configuration and data cataloging. Azure ML Pipelines brings a powerful cloud orchestration layer with managed compute, scheduling, experiment tracking, and enterprise‑grade infrastructure.

Kedro AzureML Pipeline bridges both worlds, allowing each tool to play to its strengths.

### For Kedro users

- **No code changes:** Integrate Azure ML without modifying your existing Kedro datasets, config, or pipelines.
- **Cloud orchestration:** Submit Kedro pipelines to Azure ML managed compute clusters with a single CLI command.
- **Scheduling:** Configure cron‑based schedules directly in your `azureml.yml` configuration.
- **Distributed training:** Fan out Kedro nodes across multiple GPU instances using the `@distributed_job` decorator.
- **Data asset management:** Use `AzureMLAssetDataset` to version and track data through Azure ML's data store.

Refer to the [Azure ML documentation](https://learn.microsoft.com/en-us/azure/machine-learning/) and the [Kedro Slack](https://slack.kedro.org/) to get in touch with the community.

### For Azure ML users

- **Structure your projects and configurations:** Kedro enforces a modular project structure and configuration management out of the box. By adopting Kedro, Azure ML users benefit from a standardized folder layout, environment-specific configuration files, and a clear separation between code, data, and settings. This makes it easier to manage complex projects, collaborate across teams, and maintain reproducibility across environments.
- **Straightforward pipeline creation:** Kedro makes it simple to define pipelines as sequences of modular, reusable nodes without worrying about orchestration logic. These pipelines are automatically translated into Azure ML Pipeline steps, enabling you to develop locally and immediately run on cloud compute with minimal configuration.
- **Built‑in data connectors:** Kedro's `DataCatalog` provides a centralized and declarative way to manage all data inputs and outputs across environments. It supports a wide range of data sources out of the box, from local CSVs and Parquet files to cloud storage like Azure Blob Storage and ADLS.
- **Full control over Azure ML objects:** Kedro projects are seamlessly translated into Azure ML Pipeline jobs. Any aspect of the generated jobs, compute targets, or environments can be configured in `azureml.yml` without modifying the Kedro code.

## Key features

### Configuration‑driven workflows

Centralize orchestration settings in an `azureml.yml` file, where, for each Kedro environment, you can:

- Define jobs to deploy from filtered Kedro pipelines.
- Assign compute targets and environment settings.
- Configure cron‑based schedules.

### Distributed training

Use the `@distributed_job` decorator to scale Kedro nodes across multiple compute instances. Supported frameworks include PyTorch, TensorFlow, and MPI.

### Kedro Hooks preservation

Kedro AzureML Pipeline is designed so that Kedro hooks are preserved and called at the appropriate time during pipeline execution. This ensures that any custom logic, such as data validation or logging implemented as Kedro hooks, will continue to work seamlessly when running pipelines on Azure ML.

### MLflow compatibility

Harness the capabilities of MLflow using [Kedro-MLflow](https://github.com/Galileo-Galilei/kedro-mlflow) in conjunction with Azure ML's [native MLflow integration](https://learn.microsoft.com/en-us/azure/machine-learning/how-to-use-mlflow-cli-runs). Whether you run your pipelines using Kedro or Azure ML, you can track experiments, log models, and register artifacts automatically.

### Data asset management

Use `AzureMLAssetDataset` to version and manage data through Azure ML's data store. The plugin transparently resolves data asset paths during both local and remote execution.

### Multiple workspaces

Configure multiple Azure ML workspaces and switch between them at run time. This supports multi‑environment workflows (dev, staging, production) with minimal configuration changes.

## Limitations and considerations

While Kedro AzureML Pipeline's objective is to provide a powerful bridge between Kedro and Azure ML, there are a few important points to consider:

1. **Evolving feature parity:**
   Kedro AzureML Pipeline is evolving rapidly, but as a recent package maintained as a side project, not all Azure ML features are yet exposed. We encourage you to contribute or raise issues on our [Issue Tracker](https://github.com/stateful-y/kedro-azureml-pipeline/issues) so that missing functionalities can be prioritized.

2. **Compatibility:**
   Both Kedro and the Azure ML SDK are under active development. Breaking changes in either framework can temporarily affect the plugin until a new release addresses them. Always pin your Kedro, Azure ML SDK, and Kedro AzureML Pipeline versions and test changes before upgrading.

## Contributing and community

We welcome contributions, feedback, and questions:

- **Report issues or request features:** [GitHub Issues](https://github.com/stateful-y/kedro-azureml-pipeline/issues)
- **Join the discussion:** [Kedro Slack](https://slack.kedro.org/)
- **Contributing guide:** [CONTRIBUTING.md](https://github.com/stateful-y/kedro-azureml-pipeline/blob/main/CONTRIBUTING.md)

If you are interested in becoming a maintainer of Kedro AzureML Pipeline or taking a more active role in its development, please reach out to Guillaume Tauzin on the [Kedro Slack](https://slack.kedro.org/).

---

## Next steps

- **Getting started:** Follow our step‑by‑step tutorial in [getting-started.md](getting-started.md).
- **User guide:** Dive into advanced features in the [user guide](user-guide.md).
