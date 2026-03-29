# How to Use MLflow with Azure ML

This guide shows how to track experiments with [kedro-mlflow](https://kedro-mlflow.readthedocs.io/) when running Kedro pipelines on Azure ML.

## Prerequisites

- `kedro-mlflow` installed and configured in your project
- The Kedro AzureML Pipeline plugin installed and configured (see [Getting Started](../tutorials/getting-started.md))
- The `azureml_local_run_hook` registered in `settings.py`

## Configure kedro-mlflow

Follow the standard `kedro-mlflow` setup in your project. The plugin does not replace or modify any `kedro-mlflow` configuration:

```yaml
# conf/base/mlflow.yml (kedro-mlflow configuration)
server:
  mlflow_tracking_uri: null   # Azure ML sets this at runtime
```

Azure ML injects the tracking URI automatically when the job runs on managed compute.

## Log metrics and artifacts in node functions

Use `mlflow` in your node functions as you would locally:

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

After a run completes, open Azure ML Studio and navigate to **Jobs** then your experiment. Each pipeline step appears as a child run with the Kedro node name as the run tag. Metrics, parameters, and artifacts are accessible from the run details page.

## See also

- [Architecture overview](../explanation/architecture.md#mlflow-coordination) - how the plugin coordinates MLflow during remote execution
- [kedro-mlflow documentation](https://kedro-mlflow.readthedocs.io/) - full kedro-mlflow setup and usage
- [Azure ML native MLflow integration](https://learn.microsoft.com/en-us/azure/machine-learning/how-to-use-mlflow-cli-runs) - Azure ML's MLflow tracking backend
