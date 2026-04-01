# Hook Lifecycle in Remote Execution

Kedro's hook system lets plugins and user code tap into every stage of a pipeline run, from context creation through node execution to pipeline completion. When you run a pipeline locally with `kedro run`, hooks fire in a predictable order within a single process. The natural question when moving to Azure ML is: do my hooks still work?

The short answer is yes. The plugin preserves the full Kedro hook lifecycle during remote execution. This page explains how that works and what it means for third-party hooks like `kedro-mlflow` and any custom hooks you have written.

## How remote execution bootstraps Kedro

When the plugin compiles your pipeline, each Kedro node becomes a separate Azure ML pipeline step. Each step runs in its own container on managed compute. The step's entry point is `kedro azureml execute`, which receives the node name and data paths as command-line arguments.

Inside the container, `kedro azureml execute` follows these steps:

1. Creates a [`KedroContextManager`][kedro_azureml_pipeline.manager.KedroContextManager], which loads a full `KedroSession` and fires `after_context_created`
2. Builds the `DataCatalog`, firing `after_catalog_created`
3. Passes the single-node pipeline and catalog to [`AzurePipelinesRunner`][kedro_azureml_pipeline.runner.AzurePipelinesRunner]
4. The runner fires `before_pipeline_run`, then `before_node_run`
5. For each input, fires `before_dataset_loaded` and `after_dataset_loaded`
6. Calls the node function
7. For each output, fires `before_dataset_saved` and `after_dataset_saved`
8. Fires `after_node_run`, then `after_pipeline_run`

The key insight is that `kedro azureml execute` does not bypass Kedro's session machinery. It creates a full `KedroSession`, loads the project context, builds the catalog, and runs the node through a standard Kedro runner ([`AzurePipelinesRunner`][kedro_azureml_pipeline.runner.AzurePipelinesRunner], which extends `SequentialRunner`). Every hook registered in your `settings.py` fires at the same lifecycle points as during a local run.

## Implications for custom hooks

If you have written custom hooks, they will fire during remote execution as long as they are registered in `settings.py`. A few things to be aware of:

**Hooks run once per step, not once per pipeline.** If your hook does expensive setup in `before_pipeline_run` (like opening a database connection or initializing an API client), that setup happens in every step container independently. For most hooks this is fine, but if your hook depends on shared state across nodes, the state will not carry over between steps.

**The context is fully initialized.** Your hook receives a real `KedroContext` with the project's configuration, environment settings, and catalog. The config loader respects Kedro environment layering, so `conf/local/` overrides work the same way.

**Error hooks fire correctly.** If a node raises an exception, `on_node_error` and `on_pipeline_error` both fire. Azure ML also captures the error and marks the step as failed in the pipeline graph.

**Hook ordering with `tryfirst` and `trylast` is preserved.** Kedro uses pluggy for hook management, and the `tryfirst` / `trylast` ordering directives work the same way in remote steps.

## How kedro-mlflow works remotely

The `kedro-mlflow` integration is the most common third-party hook scenario, and it requires special coordination. The challenge is that Azure ML has its own MLflow backend, and the experiment name and run ID need to be aligned between Azure ML's tracking and kedro-mlflow's expectations.

The plugin handles this through [`MlflowAzureMLHook`][kedro_azureml_pipeline.hooks.MlflowAzureMLHook], which is activated by the `KEDRO_AZUREML_MLFLOW_ENABLED=1` environment variable that the pipeline generator injects into each step.

The `tryfirst=True` directive ensures [`MlflowAzureMLHook`][kedro_azureml_pipeline.hooks.MlflowAzureMLHook] fires before kedro-mlflow's own hook. This ordering is critical because without it, Kedro-MLflow would resolve the experiment name from `mlflow.yml` (which might differ from the Azure ML job's experiment) and attempt to create a new run instead of resuming the one Azure ML already started.

The coordination works as follows:

1. The pipeline generator sets `KEDRO_AZUREML_MLFLOW_EXPERIMENT_NAME` and `MLFLOW_RUN_ID` as environment variables in each step
2. `MlflowAzureMLHook.after_context_created` copies the experiment name into `MLFLOW_EXPERIMENT_NAME`, where kedro-mlflow expects to find it
3. `MlflowAzureMLHook.before_pipeline_run` calls `mlflow.set_experiment()` and `mlflow.start_run()` with the Azure ML run ID, then tags the run with Kedro metadata (node name, pipeline name, environment)
4. kedro-mlflow's own hook then fires and finds an already-active run pointing at the correct experiment

If the step fails, `MlflowAzureMLHook.on_pipeline_error` tags the run with error details so the failure is visible in the MLflow UI.

## Writing hooks that work in both contexts

If you are writing a custom hook that needs to behave differently during local and remote runs, the simplest approach is to check the runner type in `before_pipeline_run`:

```python
from kedro.framework.hooks import hook_impl
from kedro_azureml_pipeline.runner import AzurePipelinesRunner

class MyHook:
    @hook_impl
    def before_pipeline_run(self, run_params, pipeline, catalog):
        if AzurePipelinesRunner.__name__ in run_params["runner"]:
            # Remote execution path
            ...
        else:
            # Local execution path
            ...
```

This is the same pattern the plugin's own [`AzureMLLocalRunHook`][kedro_azureml_pipeline.hooks.AzureMLLocalRunHook] uses to switch [`AzureMLAssetDataset`][kedro_azureml_pipeline.datasets.AzureMLAssetDataset] between local-intermediate and remote modes.

## Connections

- [Architecture overview](architecture.md): how hooks fit into the broader plugin design
- [How to use MLflow](../how-to/use-mlflow.md): practical setup for the kedro-mlflow integration
- [API reference](../reference/api.md): [`AzureMLLocalRunHook`][kedro_azureml_pipeline.hooks.AzureMLLocalRunHook] and [`MlflowAzureMLHook`][kedro_azureml_pipeline.hooks.MlflowAzureMLHook] class docs
