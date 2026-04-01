# How-to Guides

How-to guides are task-oriented recipes for users who already have the plugin installed and configured. Each guide solves a specific problem.

## Core workflows

- [**Schedule Pipelines**](schedule-pipelines.md): Configure cron and recurrence schedules for recurring Azure ML jobs.
- [**Use Data Assets**](use-data-assets.md): Integrate Azure ML Data Assets into your Kedro catalog with [`AzureMLAssetDataset`][kedro_azureml_pipeline.datasets.AzureMLAssetDataset] and [`AzureMLPipelineDataset`][kedro_azureml_pipeline.datasets.AzureMLPipelineDataset].
- [**Compile and Inspect**](compile-and-inspect.md): Generate Azure ML Pipeline YAML definitions and inspect them before submitting.

## Advanced features

- [**Run Distributed Training**](run-distributed-training.md): Scale Kedro nodes across multiple GPU instances with [`@distributed_job`][kedro_azureml_pipeline.distributed.distributed_job].
- [**Use MLflow**](use-mlflow.md): Track experiments with `kedro-mlflow` during Azure ML pipeline runs.
- [**Configure Multiple Workspaces**](configure-multiple-workspaces.md): Target dev, staging, and production workspaces from a single configuration.
- [**Build a Custom Environment**](build-custom-environment.md): Create and register an Azure ML environment with your project's dependencies.
- [**Deploy from CI/CD**](deploy-from-cicd.md): Submit pipeline jobs from GitHub Action or other CI/CD systems.

## Operations

- [**Authenticate**](authenticate.md): Configure Azure credentials for local development, CI/CD, and Azure ML compute.
- [**Troubleshoot**](troubleshoot.md): Diagnose common errors and debug failed pipeline runs.
- [**Contribute**](contribute.md): Set up a development environment and contribute to the project.
