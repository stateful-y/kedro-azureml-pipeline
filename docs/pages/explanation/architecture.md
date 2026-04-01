# Architecture Overview

Kedro AzureML Pipeline is a Kedro plugin that translates a Kedro project into Azure ML Pipeline jobs. It operates as a bridge layer: your Kedro code stays unchanged, and the plugin handles the translation into Azure ML's execution model.

## The two execution contexts

Your pipeline can run in two contexts.

**Local execution** (`kedro run`): Kedro runs as normal on your machine. The plugin's [`AzureMLLocalRunHook`][kedro_azureml_pipeline.hooks.AzureMLLocalRunHook] injects workspace configuration into data catalog entries that reference Azure ML assets, so that [`AzureMLAssetDataset`][kedro_azureml_pipeline.datasets.AzureMLAssetDataset] can download asset data transparently. No Azure ML compute is used.

**Remote execution** (`kedro azureml run` or `kedro azureml schedule`): The plugin compiles your Kedro pipeline into an Azure ML Pipeline YAML definition, uploads it to your workspace, and submits it. Azure ML then schedules each Kedro node as a separate pipeline step on managed compute. When using `kedro azureml schedule`, the plugin also creates an Azure ML `JobSchedule` so the pipeline runs on a cron or recurrence trigger without any local process.

## Compilation: from Kedro nodes to Azure ML steps

The [`AzureMLPipelineGenerator`][kedro_azureml_pipeline.generator.AzureMLPipelineGenerator] walks your Kedro pipeline and maps each node to an Azure ML pipeline component. For each node, it:

1. Determines inputs and outputs from the Kedro catalog
2. Rewires [`AzureMLPipelineDataset`][kedro_azureml_pipeline.datasets.AzureMLPipelineDataset] and [`AzureMLAssetDataset`][kedro_azureml_pipeline.datasets.AzureMLAssetDataset] entries to Azure ML-managed mount paths
3. Constructs a component command that calls `kedro azureml execute` with the node name
4. Applies any [`@distributed_job`][kedro_azureml_pipeline.distributed.distributed_job] decorator configuration to wrap the step as a distributed job

The result is an Azure ML Pipeline YAML definition that Azure ML can schedule, monitor, and instrument natively.

## Remote step execution

When Azure ML runs a pipeline step, it calls the internal `kedro azureml execute` command inside a container on compute. This command:

1. Loads the Kedro project context
2. Resolves dataset paths to Azure ML compute mount points (passed via `--az-input` / `--az-output` flags)
3. Runs the Kedro node through the standard Kedro runner
4. Fires all registered Kedro hooks at the appropriate lifecycle points

This means all Kedro hooks, including third-party hooks like `kedro-mlflow`, fire exactly as they would in a local run. No Azure ML-specific code is needed in your project.

## Data flow between steps

Datasets in the catalog determine how data moves between pipeline steps. The plugin provides two wrapper datasets: [`AzureMLPipelineDataset`][kedro_azureml_pipeline.datasets.AzureMLPipelineDataset] for temporary inter-step storage and [`AzureMLAssetDataset`][kedro_azureml_pipeline.datasets.AzureMLAssetDataset] for versioned Data Assets. Standard Kedro datasets travel inside the code snapshot. The [`AzurePipelinesRunner`][kedro_azureml_pipeline.runner.AzurePipelinesRunner] rewires dataset paths at runtime so your serialization logic stays unchanged.

For a deep dive into how each dataset type behaves during local and remote execution, see [Data flow between steps](data-flow.md). For usage guidance, see [How to use data assets](../how-to/use-data-assets.md). For the full parameter reference, see [Dataset reference](../reference/datasets.md).

## Hook lifecycle preservation

The full Kedro hook lifecycle is preserved during remote execution. Each step bootstraps a complete `KedroSession`, builds the catalog, and runs the node through a standard Kedro runner. All hooks registered in `settings.py` fire at the same lifecycle points as a local run, including `after_context_created`, `before_pipeline_run`, `before_node_run`, and all dataset hooks.

For a detailed walkthrough of the bootstrap sequence, hook firing order, implications for custom hooks, and how the kedro-mlflow coordination works, see [Hook lifecycle in remote execution](hook-lifecycle.md).

## MLflow coordination

When `kedro-mlflow` is installed, the pipeline generator injects `KEDRO_AZUREML_MLFLOW_ENABLED=1` into each step's environment. This activates [`MlflowAzureMLHook`][kedro_azureml_pipeline.hooks.MlflowAzureMLHook], which fires before Kedro-MLflow's own hook to pre-set `MLFLOW_EXPERIMENT_NAME`. Azure ML's native MLflow backend then records metrics and artifacts automatically. See [How to use MLflow](../how-to/use-mlflow.md) for setup instructions.

## Scheduling

The [`AzureMLScheduleClient`][kedro_azureml_pipeline.scheduler.AzureMLScheduleClient] translates the `schedule` field on a job definition into an Azure ML `JobSchedule` object, which Azure ML stores and triggers independently of the CLI. A cron or recurrence trigger fires the pipeline directly in the Azure ML service, so no local process needs to be running. See [How to schedule pipelines](../how-to/schedule-pipelines.md) for configuration steps.

## Configuration loading

The plugin reads `conf/<env>/azureml.yml` through Kedro's config loader, which means it respects all Kedro environment layering and templating. The YAML content is validated against [`KedroAzureMLConfig`][kedro_azureml_pipeline.config.KedroAzureMLConfig] (a Pydantic model), which enforces required fields and relationships such as the mandatory `__default__` workspace and compute entries. See the [Configuration reference](../reference/configuration.md) for all fields.
