# How to Use MLflow with Azure ML

This guide shows how to track experiments with [kedro-mlflow](https://kedro-mlflow.readthedocs.io/) when running Kedro pipelines on Azure ML.

## Prerequisites

- `kedro-mlflow` installed and configured in your project
- The Kedro AzureML Pipeline plugin installed and configured (see [Getting Started](../tutorials/getting-started.md))
- The `azureml_local_run_hook` registered in `settings.py`

## How the integration works

When your pipeline runs on Azure ML, the pipeline generator sets the `KEDRO_AZUREML_MLFLOW_ENABLED=1` environment variable on each pipeline step. This activates `MlflowAzureMLHook`, which:

1. Sets `MLFLOW_EXPERIMENT_NAME` before `kedro-mlflow` initialises, so runs are logged to the correct Azure ML experiment
2. Tags each MLflow child run with the Kedro node name and pipeline name

No extra configuration is needed. If `kedro-mlflow` is installed and configured, it works automatically during Azure ML runs.

## Configure kedro-mlflow as normal

Follow the standard `kedro-mlflow` setup in your project. The plugin does not replace or modify any `kedro-mlflow` configuration.

```yaml
# conf/base/mlflow.yml (kedro-mlflow configuration)
server:
  mlflow_tracking_uri: null   # Azure ML sets this at runtime
```

Azure ML injects the tracking URI automatically when the job runs on managed compute. Any `mlflow.log_metric()`, `mlflow.log_artifact()`, or other MLflow calls in your node functions log to the Azure ML experiment.

## Log metrics and artifacts in node functions

Use `mlflow` in your node functions just as you would locally:

```python
import mlflow

def train_model(X_train, y_train):
    mlflow.log_param("learning_rate", 0.01)

    model = fit(X_train, y_train)

    mlflow.log_metric("accuracy", evaluate(model, X_train, y_train))
    mlflow.log_artifact("model.pkl")

    return model
```

During local runs, these calls go to whatever tracking URI `kedro-mlflow` is configured with. During Azure ML runs, they go to your Azure ML workspace's MLflow endpoint.

## View results in Azure ML Studio

After a run completes, open Azure ML Studio and navigate to **Jobs** - your experiment. Each pipeline step appears as a child run with the Kedro node name as the run tag. Metrics, parameters, and artifacts are accessible from the run details page.

## Enable or disable for specific jobs

The `KEDRO_AZUREML_MLFLOW_ENABLED` variable is injected by the pipeline generator only during remote Azure ML execution. No action is needed to enable or disable it per job.

## See also

- [kedro-mlflow documentation](https://kedro-mlflow.readthedocs.io/) - full kedro-mlflow setup and usage
- [Azure ML native MLflow integration](https://learn.microsoft.com/en-us/azure/machine-learning/how-to-use-mlflow-cli-runs) - Azure ML's MLflow tracking backend
- [`MlflowAzureMLHook` API](../reference/api.md) - hook implementation reference
