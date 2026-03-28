# Architecture Overview

Kedro AzureML Pipeline is a Kedro plugin that translates a Kedro project into Azure ML Pipeline jobs. It operates as a bridge layer: your Kedro code stays unchanged, and the plugin handles the translation into Azure ML's execution model.

## The two execution contexts

Your pipeline can run in two contexts:

**Local execution** (`kedro run`): Kedro runs as normal on your machine. The plugin's `AzureMLLocalRunHook` injects workspace configuration into data catalog entries that reference Azure ML assets, so that `AzureMLAssetDataset` can download asset data transparently. No Azure ML compute is used.

**Remote execution** (`kedro azureml run`): The plugin compiles your Kedro pipeline into an Azure ML Pipeline YAML definition, uploads it to your workspace, and submits it. Azure ML then schedules each Kedro node as a separate pipeline step on managed compute.

## Compilation: from Kedro nodes to Azure ML steps

The `AzureMLPipelineGenerator` walks your Kedro pipeline and maps each node to an Azure ML pipeline component. For each node, it:

1. Determines inputs and outputs from the Kedro catalog
2. Rewires `AzureMLPipelineDataset` and `AzureMLAssetDataset` entries to Azure ML-managed mount paths
3. Constructs a component command that calls `kedro azureml execute` with the node name
4. Applies any `@distributed_job` decorator configuration to wrap the step as a distributed job

The result is an Azure ML Pipeline YAML definition that Azure ML can schedule, monitor, and instrument natively.

## Remote step execution

When Azure ML runs a pipeline step, it calls `kedro azureml execute` inside a container on compute. This command:

1. Loads the Kedro project context
2. Resolves dataset paths to Azure ML compute mount points (passed via `--az-input` / `--az-output` flags)
3. Runs the Kedro node through the standard Kedro runner
4. Fires all registered Kedro hooks at the appropriate lifecycle points

This means all Kedro hooks, including third-party hooks like `kedro-mlflow`, fire exactly as they would in a local run. No Azure ML-specific code is needed in your project.

## Data flow between steps

Datasets in the catalog determine how data moves between pipeline steps:

- **`AzureMLPipelineDataset`**: Azure ML mounts a temporary storage path between steps. Data is written by the producing step and read by the consuming step via mount points injected at runtime.
- **`AzureMLAssetDataset`**: Resolves to a named Azure ML Data Asset. The asset path is injected at runtime, and the underlying dataset reads from or writes to that location.
- **Standard Kedro datasets** (e.g. `pandas.CSVDataset` with a local path): The file lives inside the code snapshot or is accessed directly. This works for small files packaged with the project but is not recommended for large datasets.

## Hook lifecycle preservation

Kedro AzureML Pipeline is designed so that the full Kedro hook lifecycle is preserved during remote execution. The runner calls all hooks registered in `settings.py` at the same lifecycle points as a local run:

- `after_context_created`, `after_catalog_created`
- `before_pipeline_run`, `after_pipeline_run`, `on_pipeline_error`
- `before_node_run`, `after_node_run`, `on_node_error`
- `before_dataset_loaded`, `after_dataset_loaded`, `before_dataset_saved`, `after_dataset_saved`

## MLflow coordination

When `kedro-mlflow` is installed, the pipeline generator injects `KEDRO_AZUREML_MLFLOW_ENABLED=1` into each step's environment. This activates `MlflowAzureMLHook`, which fires before `kedro-mlflow`'s own hook to pre-set `MLFLOW_EXPERIMENT_NAME`. Azure ML's native MLflow backend then records metrics and artifacts automatically.

## Scheduling

The `AzureMLScheduler` translates the `schedule` field on a job definition into an Azure ML `JobSchedule` object, which Azure ML stores and triggers independently of the CLI. A cron or recurrence trigger fires the pipeline directly in the Azure ML service - no local process needs to be running.

## Configuration loading

The plugin reads `conf/<env>/azureml.yml` through Kedro's config loader, which means it respects all Kedro environment layering and templating. The YAML content is validated against `KedroAzureMLConfig` (a Pydantic model), which enforces required fields and relationships such as the mandatory `__default__` workspace and compute entries.
