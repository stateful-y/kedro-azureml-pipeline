![](assets/logo_dark.png#only-dark){width=800}
![](assets/logo_light.png#only-light){width=800}

# Welcome to Kedro AzureML Pipeline's documentation

Kedro AzureML Pipeline is a [Kedro](https://docs.kedro.org/) plugin that connects your data science project to [Azure ML Pipelines](https://learn.microsoft.com/en-us/azure/machine-learning/concept-ml-pipelines). With a single CLI command you can run, schedule, and monitor Kedro pipelines on Azure ML managed compute without changing any of your existing Kedro code, catalog, or hooks.

<div class="grid cards" markdown>

- **Get Started in 5 Minutes**

    ---

    Install the plugin, connect a Kedro project to your Azure ML workspace, and submit your first pipeline run to managed compute.

    [Getting Started Tutorial](pages/tutorials/getting-started.md)

- **How-to Guides**

    ---

    Task-focused recipes for scheduling runs, managing data assets, scaling with distributed training, tracking with MLflow, and deploying from CI/CD.

    [How-to Guides](pages/how-to/index.md)

- **Understand the Design**

    ---

    Learn how Kedro pipelines become Azure ML pipeline jobs and how data flows between steps.

    [Architecture](pages/explanation/index.md)

- **Reference**

    ---

    Configuration fields, CLI flags, dataset parameters, and the full Python API.

    [Reference](pages/reference/index.md)

</div>

## Key capabilities

- **No code changes**: integrate Azure ML without touching your Kedro datasets, catalog, or pipelines
- **[Scheduling](pages/how-to/schedule-pipelines.md)**: configure cron and recurrence schedules directly in `azureml.yml`
- **[Distributed training](pages/how-to/run-distributed-training.md)**: scale nodes across multiple GPU instances with `@distributed_job`
- **[Data asset management](pages/how-to/use-data-assets.md)**: version and track data through Azure ML using `AzureMLAssetDataset`
- **[Full hook lifecycle](pages/explanation/architecture.md#hook-lifecycle-preservation)**: all Kedro hooks fire during remote execution, including `kedro-mlflow`
- **[Multiple workspaces](pages/how-to/configure-multiple-workspaces.md)**: target dev, staging, and production workspaces from one config

## License

Kedro AzureML Pipeline is open source and licensed under the [Apache-2.0 License](https://opensource.org/licenses/Apache-2.0).

## Acknowledgements

This project is a fork of [kedro-azureml](https://github.com/getindata/kedro-azureml), originally developed by [GetInData](https://github.com/getindata). We are grateful for their work in creating the initial plugin that bridges Kedro and Azure ML Pipelines. We have continued development to add new features, improve documentation, and maintain the project under the `kedro-azureml-pipeline` package name.

We would also like to thank [Evolta Technologies](https://www.evolta-technologies.com/) for their support to the project.

![Evolta Technologies](assets/evolta_logo.png){width=400}

This project is maintained by [stateful-y](https://stateful-y.io), an ML consultancy specializing in MLOps and data science & engineering.

![Made by stateful-y](assets/made_by_stateful-y.png){width=200}
