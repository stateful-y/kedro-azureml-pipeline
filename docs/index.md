![](assets/logo_dark.png#only-dark){width=800}
![](assets/logo_light.png#only-light){width=800}

# Kedro AzureML Pipeline

Kedro AzureML Pipeline is a Kedro plugin that connects your data science project to [Azure ML Pipelines](https://learn.microsoft.com/en-us/azure/machine-learning/concept-ml-pipelines). With a single CLI command you can run, schedule, and monitor Kedro pipelines on Azure ML managed compute - without changing any of your existing Kedro code, catalog, or hooks.

<div class="grid cards" markdown>

- **New here?**

    ---

    Deploy your first Kedro pipeline to Azure ML in one guided walkthrough.

    [Getting Started Tutorial](pages/tutorials/getting-started.md)

- **Doing something specific?**

    ---

    Step-by-step instructions for scheduling, data assets, distributed training, MLflow, and more.

    [How-to Guides](pages/how-to/schedule-pipelines.md)

- **Looking something up?**

    ---

    Complete field tables for `azureml.yml` and all CLI flags.

    [Configuration Reference](pages/reference/configuration.md) - [CLI Reference](pages/reference/cli.md)

- **Curious how it works?**

    ---

    Understand how the plugin translates Kedro into Azure ML steps and preserves your hooks.

    [Architecture](pages/explanation/architecture.md)

</div>

## Key capabilities

- **No code changes** - integrate Azure ML without touching your Kedro datasets, catalog, or pipelines
- **Scheduling** - configure cron and recurrence schedules directly in `azureml.yml`
- **Distributed training** - scale nodes across multiple GPU instances with `@distributed_job`
- **Data asset management** - version and track data through Azure ML using `AzureMLAssetDataset`
- **Full hook lifecycle** - all Kedro hooks fire during remote execution, including `kedro-mlflow`
- **Multiple workspaces** - target dev, staging, and production workspaces from one config

## Documentation

### Tutorials

- [Getting Started](pages/tutorials/getting-started.md) - deploy your first pipeline end-to-end

### How-to Guides

- [Schedule Pipelines](pages/how-to/schedule-pipelines.md)
- [Use Data Assets](pages/how-to/use-data-assets.md)
- [Run Distributed Training](pages/how-to/run-distributed-training.md)
- [Use MLflow](pages/how-to/use-mlflow.md)
- [Configure Multiple Workspaces](pages/how-to/configure-multiple-workspaces.md)
- [Troubleshoot](pages/how-to/troubleshoot.md)
- [Contribute](pages/how-to/contribute.md)

### Reference

- [Configuration Reference](pages/reference/configuration.md)
- [CLI Reference](pages/reference/cli.md)
- [API Reference](pages/reference/api.md)

### Explanation

- [Architecture](pages/explanation/architecture.md)

## License

Kedro AzureML Pipeline is open source and licensed under the [Apache-2.0 License](https://opensource.org/licenses/Apache-2.0).
